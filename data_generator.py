"""
data_generator.py — v2
擴充版:800筆交易 / 100員工 / 加入誘惑陷阱與替代解釋機制

新增機制:
- 空頭新聞事件(對稱測試)
- 產業普漲期(替代解釋)
- DECOY_CLEAN 標籤:高風險外觀但實際應判 CLEAN 的案例
- 新聞前天數分布拉滿 1-7 天(邊界測試)
"""

import random
import json
from datetime import date, time, timedelta
from typing import List, Tuple, Dict
from schema import (
    Employee, Trade, TradeSide, Department, AccessLevel,
    RestrictedListEntry, RestrictionReason, NewsEvent
)

SEED = 42
random.seed(SEED)

# ------------------------------
# 靜態資料
# ------------------------------

TICKER_UNIVERSE = [
    "0700.HK", "9988.HK", "0005.HK", "3690.HK", "1810.HK",
    "0388.HK", "0011.HK", "0175.HK", "1211.HK", "0939.HK",
    "2318.HK", "0027.HK"
]

# 產業歸類 — 用於「產業普漲」替代解釋
TECH_TICKERS = {"0700.HK", "9988.HK", "3690.HK", "1810.HK"}
FINANCIAL_TICKERS = {"0005.HK", "0388.HK", "0939.HK", "2318.HK"}

# 產業普漲期(對齊後續 TECH BULL 新聞窗口,讓 DECOY_SECTOR_RALLY 能進入 LLM 審查)
SECTOR_RALLY_PERIODS = [
    # TECH rally 1:對齊 1810.HK (Xiaomi) 5/22 利多新聞
    (date(2026, 5, 15), date(2026, 5, 21), "TECH", TECH_TICKERS),
    # TECH rally 2:對齊 3690.HK (Meituan) 6/25 利多新聞
    (date(2026, 6, 18), date(2026, 6, 24), "TECH", TECH_TICKERS),
]

RESTRICTED_LIST = [
    RestrictedListEntry(
        ticker="0700.HK",
        restriction_start=date(2026, 3, 1),
        restriction_end=date(2026, 5, 31),
        reason=RestrictionReason.DEAL,
    ),
    RestrictedListEntry(
        ticker="9988.HK",
        restriction_start=date(2026, 4, 15),
        restriction_end=date(2026, 6, 15),
        reason=RestrictionReason.INSIDER_INFO,
    ),
]

BLACKOUT_PERIODS: Dict[str, List[Tuple[date, date]]] = {
    "0700.HK": [(date(2026, 5, 1), date(2026, 5, 15))],
    "9988.HK": [(date(2026, 5, 8), date(2026, 5, 22))],
    "3690.HK": [(date(2026, 5, 15), date(2026, 5, 29))],
}

# 新聞事件 — 混合利多與空頭
NEWS_EVENTS = [
    # 舊的三個(保留,不動)
    NewsEvent(ticker="1211.HK", event_date=date(2026, 4, 20),
              event_type="profit_alert",
              headline="BYD announces record Q1 EV sales, beating estimates by 30%",
              price_move_pct=8.5),
    NewsEvent(ticker="0175.HK", event_date=date(2026, 6, 3),
              event_type="M&A",
              headline="Geely to acquire European auto brand — deal valued at USD 2B",
              price_move_pct=12.0),
    NewsEvent(ticker="1810.HK", event_date=date(2026, 5, 22),
              event_type="earnings",
              headline="Xiaomi Q1 revenue surges 45% YoY on smartphone comeback",
              price_move_pct=6.2),
    # 新增:空頭事件(用於對稱測試)
    NewsEvent(ticker="0388.HK", event_date=date(2026, 4, 8),
              event_type="profit_warning",
              headline="HKEX warns Q1 profit to fall 25% on weak trading volumes",
              price_move_pct=-7.8),
    NewsEvent(ticker="0027.HK", event_date=date(2026, 5, 12),
              event_type="regulatory_probe",
              headline="Galaxy Entertainment under investigation for AML compliance",
              price_move_pct=-9.5),
    # 新增:再多一個利多(讓LLM審查量夠大)
    NewsEvent(ticker="3690.HK", event_date=date(2026, 6, 25),
              event_type="earnings_beat",
              headline="Meituan Q2 revenue beats consensus by 15%",
              price_move_pct=5.8),
]

HOLDING_PERIOD_DAYS = 30
DATE_START = date(2026, 1, 1)
DATE_END = date(2026, 6, 30)


# ------------------------------
# 輔助
# ------------------------------

def random_date_between(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def random_time() -> time:
    return time(random.randint(9, 15), random.randint(0, 59))


def is_in_restricted_list(ticker: str, trade_date: date) -> bool:
    return any(r.ticker == ticker and r.restriction_start <= trade_date <= r.restriction_end
               for r in RESTRICTED_LIST)


def is_in_blackout(ticker: str, trade_date: date) -> bool:
    return any(start <= trade_date <= end
               for start, end in BLACKOUT_PERIODS.get(ticker, []))


def is_in_sector_rally(ticker: str, trade_date: date) -> Tuple[bool, str]:
    for start, end, name, tickers in SECTOR_RALLY_PERIODS:
        if ticker in tickers and start <= trade_date <= end:
            return True, name
    return False, ""


# ------------------------------
# 員工生成
# ------------------------------

DEPT_PROFILES = [
    (Department.RESEARCH, AccessLevel.MEDIUM, "Analyst", True),
    (Department.RESEARCH, AccessLevel.HIGH, "Senior Analyst", True),
    (Department.INVESTMENT_BANKING, AccessLevel.HIGH, "VP", False),
    (Department.INVESTMENT_BANKING, AccessLevel.HIGH, "Associate", False),
    (Department.ASSET_MANAGEMENT, AccessLevel.MEDIUM, "Portfolio Manager", False),
    (Department.SALES_TRADING, AccessLevel.MEDIUM, "Sales", False),
    (Department.COMPLIANCE, AccessLevel.LOW, "Compliance Analyst", False),
    (Department.BACK_OFFICE, AccessLevel.LOW, "Operations Officer", False),
]

FIRST_NAMES = ["Alice", "Brian", "Cathy", "David", "Emily", "Frank",
               "Grace", "Henry", "Ivy", "Jason", "Kelly", "Leo",
               "Mandy", "Nathan", "Olivia", "Peter", "Queenie", "Ryan",
               "Sophie", "Tom", "Uma", "Victor", "Wendy", "Xavier"]
LAST_NAMES = ["Chan", "Wong", "Lee", "Cheung", "Ng", "Lam", "Tang", "Ho",
              "Choi", "Yeung", "Kwok", "Fung"]


def generate_employees(n: int) -> List[Employee]:
    employees = []
    for i in range(n):
        dept, access, role, has_coverage = random.choice(DEPT_PROFILES)
        covered = random.sample(TICKER_UNIVERSE, k=random.randint(2, 4)) if has_coverage else []
        employees.append(Employee(
            employee_id=f"EMP{i+1:04d}",
            name=f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
            department=dept,
            role=role,
            access_level=access,
            covered_stocks=covered,
            hire_date=date(2020, 1, 1) + timedelta(days=random.randint(0, 1500))
        ))
    return employees


# ------------------------------
# 交易 / 違規注入
# ------------------------------

def _tid(counter: List[int]) -> str:
    counter[0] += 1
    return f"TRD{counter[0]:05d}"


def _pc_id() -> str:
    return f"PC{random.randint(10000, 99999)}"


def generate_clean_trade(emp: Employee, counter: List[int]) -> Trade:
    candidates = [t for t in TICKER_UNIVERSE if t not in emp.covered_stocks]
    ticker = random.choice(candidates)
    for _ in range(50):
        d = random_date_between(DATE_START, DATE_END)
        if not is_in_restricted_list(ticker, d) and not is_in_blackout(ticker, d):
            break
    return Trade(
        trade_id=_tid(counter),
        employee_id=emp.employee_id,
        ticker=ticker,
        side=random.choice([TradeSide.BUY, TradeSide.SELL]),
        quantity=random.choice([100, 500, 1000, 2000, 5000]),
        trade_date=d,
        trade_time=random_time(),
        price=round(random.uniform(50, 500), 2),
        pre_cleared=True,
        pre_clearance_id=_pc_id(),
    )


def inject_restricted_list(emp, counter):
    r = random.choice(RESTRICTED_LIST)
    d = random_date_between(r.restriction_start, r.restriction_end)
    return Trade(
        trade_id=_tid(counter), employee_id=emp.employee_id, ticker=r.ticker,
        side=random.choice([TradeSide.BUY, TradeSide.SELL]),
        quantity=random.choice([500, 1000, 2000]),
        trade_date=d, trade_time=random_time(),
        price=round(random.uniform(50, 500), 2),
        pre_cleared=True, pre_clearance_id=_pc_id()
    ), ["RESTRICTED_LIST"]


def inject_no_preclearance(emp, counter):
    ticker = random.choice([t for t in TICKER_UNIVERSE if t not in emp.covered_stocks])
    return Trade(
        trade_id=_tid(counter), employee_id=emp.employee_id, ticker=ticker,
        side=random.choice([TradeSide.BUY, TradeSide.SELL]),
        quantity=random.choice([500, 1000]),
        trade_date=random_date_between(DATE_START, DATE_END),
        trade_time=random_time(),
        price=round(random.uniform(50, 500), 2),
        pre_cleared=False
    ), ["NO_PRECLEARANCE"]


def inject_holding_period(emp, counter):
    ticker = random.choice([t for t in TICKER_UNIVERSE if t not in emp.covered_stocks])
    buy_date = random_date_between(DATE_START, DATE_END - timedelta(days=40))
    sell_date = buy_date + timedelta(days=random.randint(3, HOLDING_PERIOD_DAYS - 1))
    price = round(random.uniform(50, 500), 2)
    buy = Trade(trade_id=_tid(counter), employee_id=emp.employee_id, ticker=ticker,
                side=TradeSide.BUY, quantity=1000, trade_date=buy_date,
                trade_time=random_time(), price=price,
                pre_cleared=True, pre_clearance_id=_pc_id())
    sell = Trade(trade_id=_tid(counter), employee_id=emp.employee_id, ticker=ticker,
                 side=TradeSide.SELL, quantity=1000, trade_date=sell_date,
                 trade_time=random_time(),
                 price=round(price * random.uniform(0.9, 1.1), 2),
                 pre_cleared=True, pre_clearance_id=_pc_id())
    return [buy, sell], [[], ["HOLDING_PERIOD"]]


def inject_blackout(emp, counter):
    ticker = random.choice(list(BLACKOUT_PERIODS.keys()))
    start, end = BLACKOUT_PERIODS[ticker][0]
    return Trade(
        trade_id=_tid(counter), employee_id=emp.employee_id, ticker=ticker,
        side=random.choice([TradeSide.BUY, TradeSide.SELL]),
        quantity=1000, trade_date=random_date_between(start, end),
        trade_time=random_time(),
        price=round(random.uniform(50, 500), 2),
        pre_cleared=True, pre_clearance_id=_pc_id()
    ), ["BLACKOUT_PERIOD"]


def inject_covered_stock(emp, counter):
    if not emp.covered_stocks:
        return None, None
    return Trade(
        trade_id=_tid(counter), employee_id=emp.employee_id,
        ticker=random.choice(emp.covered_stocks),
        side=random.choice([TradeSide.BUY, TradeSide.SELL]),
        quantity=1000, trade_date=random_date_between(DATE_START, DATE_END),
        trade_time=random_time(),
        price=round(random.uniform(50, 500), 2),
        pre_cleared=True, pre_clearance_id=_pc_id()
    ), ["COVERED_STOCK"]


# --- PRE_NEWS_SUSPECT:改為天數分布1-7,方向依新聞方向決定 ---
def inject_pre_news(emp, counter):
    """真違規:MNPI 濫用者在新聞前 1-5 天,方向一致地建倉。"""
    event = random.choice(NEWS_EVENTS)
    days_before = random.randint(1, 5)   # 對齊 prompt 的可疑窗口
    trade_date = event.event_date - timedelta(days=days_before)
    # 方向一致:利多前買、利空前賣
    side = TradeSide.BUY if event.price_move_pct > 0 else TradeSide.SELL
    return Trade(
        trade_id=_tid(counter), employee_id=emp.employee_id, ticker=event.ticker,
        side=side, quantity=random.choice([2000, 5000]),
        trade_date=trade_date, trade_time=random_time(),
        price=round(random.uniform(50, 500), 2),
        pre_cleared=True, pre_clearance_id=_pc_id()
    ), ["PRE_NEWS_SUSPECT"]


# --- 新增:B類 誘惑陷阱 — HIGH access + 時間近但方向錯 ---
def inject_decoy_wrong_direction(emp, counter):
    """HIGH access員工,新聞前1-3天,但方向與新聞相反 → 應判 CLEAN"""
    high_events = [e for e in NEWS_EVENTS]  # 隨機挑
    event = random.choice(high_events)
    days_before = random.randint(1, 3)
    trade_date = event.event_date - timedelta(days=days_before)
    # 方向刻意錯:利多前賣、利空前買
    side = TradeSide.SELL if event.price_move_pct > 0 else TradeSide.BUY
    return Trade(
        trade_id=_tid(counter), employee_id=emp.employee_id, ticker=event.ticker,
        side=side, quantity=random.choice([1000, 2000]),
        trade_date=trade_date, trade_time=random_time(),
        price=round(random.uniform(50, 500), 2),
        pre_cleared=True, pre_clearance_id=_pc_id()
    ), ["DECOY_WRONG_DIRECTION"]


# --- 新增:C類 誘惑陷阱 — LOW access但完美條件 ---
def inject_decoy_low_access(emp, counter):
    """LOW access員工,新聞前1-3天,方向一致,大額 → 應判 CLEAN 或 REQUIRES_REVIEW"""
    event = random.choice(NEWS_EVENTS)
    days_before = random.randint(1, 3)
    trade_date = event.event_date - timedelta(days=days_before)
    side = TradeSide.BUY if event.price_move_pct > 0 else TradeSide.SELL
    return Trade(
        trade_id=_tid(counter), employee_id=emp.employee_id, ticker=event.ticker,
        side=side, quantity=5000,  # 大額
        trade_date=trade_date, trade_time=random_time(),
        price=round(random.uniform(50, 500), 2),
        pre_cleared=True, pre_clearance_id=_pc_id()
    ), ["DECOY_LOW_ACCESS"]


# --- 新增:D類 替代解釋 — 產業普漲期買入該產業股票 ---
def inject_decoy_sector_rally(emp, counter):
    """替代解釋陷阱:產業普漲期買入該產業有後續利多新聞的股票 → 應判 CLEAN。"""
    period = random.choice(SECTOR_RALLY_PERIODS)
    start, end, sector_name, tickers = period
    # 挑選 rally 結束後 7 天內有 BULL 新聞的 ticker
    valid_tickers = [
        e.ticker for e in NEWS_EVENTS
        if e.ticker in tickers
        and e.price_move_pct > 0
        and 0 <= (e.event_date - end).days <= 7
    ]
    if valid_tickers:
        ticker = random.choice(valid_tickers)
    else:
        ticker = random.choice(list(tickers))
    d = random_date_between(start, end)
    # 避開限制期與黑箱期,避免污染其他違規類型
    for _ in range(20):
        if not is_in_restricted_list(ticker, d) and not is_in_blackout(ticker, d):
            break
        d = random_date_between(start, end)
    return Trade(
        trade_id=_tid(counter), employee_id=emp.employee_id, ticker=ticker,
        side=TradeSide.BUY, quantity=random.choice([2000, 5000]),
        trade_date=d, trade_time=random_time(),
        price=round(random.uniform(50, 500), 2),
        pre_cleared=True, pre_clearance_id=_pc_id()
    ), ["DECOY_SECTOR_RALLY"]


# ------------------------------
# 主生成器
# ------------------------------

def generate_dataset(n_trades: int = 800, violation_rate: float = 0.20,
                     decoy_rate: float = 0.08):
    """
    n_trades: 總交易數
    violation_rate: 真違規比例(硬規則 + PRE_NEWS_SUSPECT)
    decoy_rate: 誘惑陷阱比例(高風險外觀但應判 CLEAN)
    """
    employees = generate_employees(100)
    counter = [0]
    trades: List[Trade] = []
    ground_truth: Dict[str, List[str]] = {}

    n_violations = int(n_trades * violation_rate)   # 160筆
    n_decoys = int(n_trades * decoy_rate)           # 64筆
    n_clean = n_trades - n_violations - n_decoys    # 576筆

    # 真違規類型 quota
    violation_types = ["RESTRICTED_LIST", "NO_PRECLEARANCE", "HOLDING_PERIOD",
                       "BLACKOUT_PERIOD", "COVERED_STOCK", "PRE_NEWS_SUSPECT"]
    quota = {v: n_violations // len(violation_types) for v in violation_types}
    remaining = n_violations - sum(quota.values())
    for _ in range(remaining):
        quota[random.choice(violation_types)] += 1
    # 讓 PRE_NEWS_SUSPECT 多一些,好餵給 LLM
    quota["PRE_NEWS_SUSPECT"] += 8

    # 誘惑陷阱 quota
    decoy_types = ["DECOY_WRONG_DIRECTION", "DECOY_LOW_ACCESS", "DECOY_SECTOR_RALLY"]
    decoy_quota = {d: n_decoys // len(decoy_types) for d in decoy_types}
    remaining_d = n_decoys - sum(decoy_quota.values())
    for _ in range(remaining_d):
        decoy_quota[random.choice(decoy_types)] += 1

    injectors = {
        "RESTRICTED_LIST": inject_restricted_list,
        "NO_PRECLEARANCE": inject_no_preclearance,
        "BLACKOUT_PERIOD": inject_blackout,
        "COVERED_STOCK": inject_covered_stock,
        "PRE_NEWS_SUSPECT": inject_pre_news,
        "DECOY_WRONG_DIRECTION": inject_decoy_wrong_direction,
        "DECOY_SECTOR_RALLY": inject_decoy_sector_rally,
    }

  # === 注入真違規(單筆)===
    non_low_emps = [e for e in employees if e.access_level != AccessLevel.LOW]
    for vtype, count in quota.items():
        if vtype == "HOLDING_PERIOD":
            continue
        for _ in range(count):
            emp = random.choice(employees)
            if vtype == "COVERED_STOCK":
                research_emps = [e for e in employees if e.covered_stocks]
                if research_emps:
                    emp = random.choice(research_emps)
            elif vtype == "PRE_NEWS_SUSPECT":
                # 方法論:LOW access 缺乏 MNPI 管道,不應被標為真違規(概念上與 DECOY_LOW_ACCESS 衝突)
                if non_low_emps:
                    emp = random.choice(non_low_emps)
            trade, flags = injectors[vtype](emp, counter)
            if trade is not None:
                trades.append(trade)
                ground_truth[trade.trade_id] = flags

    # === HOLDING_PERIOD(雙筆)===
    for _ in range(quota["HOLDING_PERIOD"]):
        emp = random.choice(employees)
        pair_trades, pair_flags = inject_holding_period(emp, counter)
        for t, f in zip(pair_trades, pair_flags):
            trades.append(t)
            ground_truth[t.trade_id] = f

    # === 注入誘惑陷阱 ===
    high_emps = [e for e in employees if e.access_level == AccessLevel.HIGH]
    low_emps = [e for e in employees if e.access_level == AccessLevel.LOW]

    for _ in range(decoy_quota["DECOY_WRONG_DIRECTION"]):
        if not high_emps:
            continue
        emp = random.choice(high_emps)
        t, f = inject_decoy_wrong_direction(emp, counter)
        trades.append(t)
        ground_truth[t.trade_id] = f

    for _ in range(decoy_quota["DECOY_LOW_ACCESS"]):
        if not low_emps:
            continue
        emp = random.choice(low_emps)
        t, f = inject_decoy_low_access(emp, counter)
        trades.append(t)
        ground_truth[t.trade_id] = f

    for _ in range(decoy_quota["DECOY_SECTOR_RALLY"]):
        emp = random.choice(employees)
        t, f = inject_decoy_sector_rally(emp, counter)
        trades.append(t)
        ground_truth[t.trade_id] = f

    # === 補足乾淨交易 ===
    while len(trades) < n_trades:
        emp = random.choice(employees)
        t = generate_clean_trade(emp, counter)
        trades.append(t)
        ground_truth[t.trade_id] = []

    trades.sort(key=lambda x: (x.trade_date, x.trade_time))
    return employees, trades, ground_truth


def dump_dataset():
    employees, trades, ground_truth = generate_dataset()

    with open("employees.json", "w", encoding="utf-8") as f:
        json.dump([e.model_dump(mode="json") for e in employees], f,
                  ensure_ascii=False, indent=2)
    with open("trades.json", "w", encoding="utf-8") as f:
        json.dump([t.model_dump(mode="json") for t in trades], f,
                  ensure_ascii=False, indent=2)
    with open("ground_truth.json", "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, ensure_ascii=False, indent=2)

    from collections import Counter
    n_total = len(trades)
    n_violations = sum(1 for v in ground_truth.values()
                       if any(f in ["RESTRICTED_LIST", "NO_PRECLEARANCE",
                                    "HOLDING_PERIOD", "BLACKOUT_PERIOD",
                                    "COVERED_STOCK", "PRE_NEWS_SUSPECT"] for f in v))
    n_decoys = sum(1 for v in ground_truth.values()
                   if any(f.startswith("DECOY") for f in v))
    all_flags = [f for flags in ground_truth.values() for f in flags]
    breakdown = Counter(all_flags)

    print(f"生成完成: {n_total} 筆交易, {len(employees)} 位員工")
    print(f"真違規筆數: {n_violations} ({n_violations/n_total:.1%})")
    print(f"誘惑陷阱筆數: {n_decoys} ({n_decoys/n_total:.1%})")
    print("\n類型分布:")
    for k, v in breakdown.most_common():
        print(f"  {k:28s} {v}")


if __name__ == "__main__":
    dump_dataset()