"""
rule_engine.py
PAD 合規審查 — 決定性規則引擎(第一層)。

設計原則:
- 每條規則獨立函式,回傳 List[RuleFlag] (可能命中 0 或多條)
- 一筆交易可能觸發多條規則(真實場景)
- 所有靜態資料(限制清單、黑箱期、持有期天數)從 data_generator 匯入
  → 若未來搬到 config 檔案,只改一處
"""

from typing import List, Dict
from datetime import timedelta
from schema import (
    Trade, Employee, RuleFlag, TradeSide,
    RestrictedListEntry
)
from data_generator import (
    RESTRICTED_LIST, BLACKOUT_PERIODS, HOLDING_PERIOD_DAYS
)


# ------------------------------
# 單條規則:一次判斷一筆交易
# ------------------------------

def rule_PAD001_restricted_list(trade: Trade) -> List[RuleFlag]:
    """PAD001:交易日在該股的限制清單期間內。"""
    for r in RESTRICTED_LIST:
        if r.ticker == trade.ticker and r.restriction_start <= trade.trade_date <= r.restriction_end:
            return [RuleFlag(
                rule_code="PAD001",
                rule_name="Restricted List Violation",
                severity="HIGH",
                detail=(
                    f"{trade.ticker} 於 {r.restriction_start}~{r.restriction_end} "
                    f"列於限制清單(原因: {r.reason.value}),但員工於 {trade.trade_date} 進行交易。"
                )
            )]
    return []


def rule_PAD002_no_preclearance(trade: Trade) -> List[RuleFlag]:
    """PAD002:未經預先申報即進行交易。"""
    if not trade.pre_cleared:
        return [RuleFlag(
            rule_code="PAD002",
            rule_name="No Pre-Clearance",
            severity="HIGH",
            detail=f"交易 {trade.trade_id} 未提供預先申報記錄。"
        )]
    return []


def rule_PAD003_blackout(trade: Trade) -> List[RuleFlag]:
    """PAD003:交易日落在該股的黑箱期內。"""
    for start, end in BLACKOUT_PERIODS.get(trade.ticker, []):
        if start <= trade.trade_date <= end:
            return [RuleFlag(
                rule_code="PAD003",
                rule_name="Blackout Period Violation",
                severity="HIGH",
                detail=(
                    f"{trade.ticker} 於 {start}~{end} 為黑箱期,"
                    f"員工於 {trade.trade_date} 進行交易。"
                )
            )]
    return []


def rule_PAD004_covered_stock(trade: Trade, employee: Employee) -> List[RuleFlag]:
    """PAD004:分析師交易自己覆蓋的個股(利益衝突)。"""
    if trade.ticker in employee.covered_stocks:
        return [RuleFlag(
            rule_code="PAD004",
            rule_name="Covered Stock Conflict",
            severity="MEDIUM",
            detail=(
                f"員工 {employee.name} ({employee.role}) 覆蓋 {trade.ticker},"
                f"不得自行交易該股。"
            )
        )]
    return []


def rule_PAD005_holding_period(
    trade: Trade,
    employee_trades: List[Trade]
) -> List[RuleFlag]:
    """
    PAD005:賣出動作違反持有期(< HOLDING_PERIOD_DAYS 天)。
    需要查閱該員工過去在同一支股票的買入紀錄。
    """
    if trade.side != TradeSide.SELL:
        return []

    # 找出同員工、同標的、日期在本筆之前、且為 BUY 的交易
    prior_buys = [
        t for t in employee_trades
        if t.ticker == trade.ticker
        and t.side == TradeSide.BUY
        and t.trade_date < trade.trade_date
    ]
    if not prior_buys:
        return []

    # 取最近一筆買入
    most_recent_buy = max(prior_buys, key=lambda x: x.trade_date)
    days_held = (trade.trade_date - most_recent_buy.trade_date).days

    if days_held < HOLDING_PERIOD_DAYS:
        return [RuleFlag(
            rule_code="PAD005",
            rule_name="Holding Period Violation",
            severity="MEDIUM",
            detail=(
                f"員工於 {most_recent_buy.trade_date} 買入 {trade.ticker},"
                f"於 {trade.trade_date} 賣出(僅持有 {days_held} 天,"
                f"低於 {HOLDING_PERIOD_DAYS} 天門檻)。"
            )
        )]
    return []


# ------------------------------
# 主管線
# ------------------------------

def evaluate_trade(
    trade: Trade,
    employee: Employee,
    employee_trades: List[Trade]
) -> List[RuleFlag]:
    """對單筆交易跑完所有規則。"""
    flags: List[RuleFlag] = []
    flags += rule_PAD001_restricted_list(trade)
    flags += rule_PAD002_no_preclearance(trade)
    flags += rule_PAD003_blackout(trade)
    flags += rule_PAD004_covered_stock(trade, employee)
    flags += rule_PAD005_holding_period(trade, employee_trades)
    return flags


def evaluate_all(
    trades: List[Trade],
    employees: List[Employee]
) -> Dict[str, List[RuleFlag]]:
    """對整批交易跑規則引擎,回傳 {trade_id: [flags]}"""
    emp_lookup = {e.employee_id: e for e in employees}
    # 預先分組:同員工的所有交易(供 PAD005 查詢)
    by_employee: Dict[str, List[Trade]] = {}
    for t in trades:
        by_employee.setdefault(t.employee_id, []).append(t)

    results: Dict[str, List[RuleFlag]] = {}
    for t in trades:
        emp = emp_lookup.get(t.employee_id)
        if emp is None:
            continue
        emp_trades = by_employee.get(t.employee_id, [])
        results[t.trade_id] = evaluate_trade(t, emp, emp_trades)
    return results


# ------------------------------
# 主程式:載入資料,跑規則,對照 ground truth
# ------------------------------

if __name__ == "__main__":
    import json
    from collections import Counter
    from datetime import timedelta
    from schema import TradeSide

    with open("employees.json", "r", encoding="utf-8") as f:
        employees = [Employee(**e) for e in json.load(f)]
    with open("trades.json", "r", encoding="utf-8") as f:
        trades = [Trade(**t) for t in json.load(f)]
    with open("ground_truth.json", "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    results = evaluate_all(trades, employees)

    flag_counter = Counter()
    for flags in results.values():
        for f in flags:
            flag_counter[f.rule_code] += 1

    n_flagged = sum(1 for f in results.values() if f)
    print(f"規則引擎審查完成: {len(trades)} 筆交易")
    print(f"被 flag 交易數: {n_flagged}")
    print("規則命中分布:")
    for code, count in flag_counter.most_common():
        print(f"  {code}  {count}")

    RULE_TO_GT = {
        "PAD001": "RESTRICTED_LIST",
        "PAD002": "NO_PRECLEARANCE",
        "PAD003": "BLACKOUT_PERIOD",
        "PAD004": "COVERED_STOCK",
        "PAD005": "HOLDING_PERIOD",
    }

    # ------------------------------
    # 建立「該交易的所有可證實違規」— 不只看 GT 標籤,還檢查客觀事實
    # ------------------------------
    from data_generator import RESTRICTED_LIST, BLACKOUT_PERIODS, HOLDING_PERIOD_DAYS

    emp_lookup = {e.employee_id: e for e in employees}
    trade_lookup = {t.trade_id: t for t in trades}
    by_employee = {}
    for t in trades:
        by_employee.setdefault(t.employee_id, []).append(t)

    def actual_violations(trade: Trade) -> set:
        """獨立地檢查一筆交易客觀上違反了哪些規則。"""
        emp = emp_lookup[trade.employee_id]
        vios = set()
        # RESTRICTED_LIST
        for r in RESTRICTED_LIST:
            if r.ticker == trade.ticker and r.restriction_start <= trade.trade_date <= r.restriction_end:
                vios.add("RESTRICTED_LIST")
        # NO_PRECLEARANCE
        if not trade.pre_cleared:
            vios.add("NO_PRECLEARANCE")
        # BLACKOUT_PERIOD
        for start, end in BLACKOUT_PERIODS.get(trade.ticker, []):
            if start <= trade.trade_date <= end:
                vios.add("BLACKOUT_PERIOD")
        # COVERED_STOCK
        if trade.ticker in emp.covered_stocks:
            vios.add("COVERED_STOCK")
        # HOLDING_PERIOD
        if trade.side == TradeSide.SELL:
            prior_buys = [x for x in by_employee[trade.employee_id]
                          if x.ticker == trade.ticker and x.side == TradeSide.BUY
                          and x.trade_date < trade.trade_date]
            if prior_buys:
                most_recent = max(prior_buys, key=lambda x: x.trade_date)
                if (trade.trade_date - most_recent.trade_date).days < HOLDING_PERIOD_DAYS:
                    vios.add("HOLDING_PERIOD")
        return vios

    tp = fp = fn = 0
    for trade_id, flags in results.items():
        detected = {RULE_TO_GT[f.rule_code] for f in flags}
        actual = actual_violations(trade_lookup[trade_id])
        # 只評估硬規則(排除 PRE_NEWS_SUSPECT,那是 LLM 職責)
        tp += len(detected & actual)
        fp += len(detected - actual)
        fn += len(actual - detected)

    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0

    print("\n=== 規則引擎 vs 客觀事實(所有硬規則違規)===")
    print(f"True Positives:  {tp}")
    print(f"False Positives: {fp}")
    print(f"False Negatives: {fn}")
    print(f"Precision: {precision:.2%}")
    print(f"Recall:    {recall:.2%}")
    print(f"F1 Score:  {f1:.2%}")