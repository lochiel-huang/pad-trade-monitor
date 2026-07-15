"""
diagnose_fp.py
把 rule engine 認為違規但 ground truth 沒標的交易列出來,分類原因。
"""

import json
from schema import Employee, Trade
from rule_engine import evaluate_all

with open("employees.json", "r", encoding="utf-8") as f:
    employees = [Employee(**e) for e in json.load(f)]
with open("trades.json", "r", encoding="utf-8") as f:
    trades = [Trade(**t) for t in json.load(f)]
with open("ground_truth.json", "r", encoding="utf-8") as f:
    ground_truth = json.load(f)

results = evaluate_all(trades, employees)

RULE_TO_GT = {
    "PAD001": "RESTRICTED_LIST",
    "PAD002": "NO_PRECLEARANCE",
    "PAD003": "BLACKOUT_PERIOD",
    "PAD004": "COVERED_STOCK",
    "PAD005": "HOLDING_PERIOD",
}

trade_lookup = {t.trade_id: t for t in trades}
emp_lookup = {e.employee_id: e for e in employees}

print("=" * 70)
print("誤報診斷 — 規則命中但 ground truth 未標記的案例")
print("=" * 70)

fp_count = 0
for trade_id, flags in results.items():
    truth = set(ground_truth.get(trade_id, []))
    truth_hard = {t for t in truth if t != "PRE_NEWS_SUSPECT"}
    detected = {RULE_TO_GT[f.rule_code] for f in flags}
    fp_types = detected - truth_hard
    if not fp_types:
        continue
    fp_count += 1
    t = trade_lookup[trade_id]
    emp = emp_lookup[t.employee_id]
    print(f"\n[{fp_count}] Trade {trade_id}")
    print(f"    員工: {emp.name} ({emp.department.value}, covers: {emp.covered_stocks})")
    print(f"    交易: {t.side.value} {t.ticker} on {t.trade_date} qty={t.quantity} pre_cleared={t.pre_cleared}")
    print(f"    GT 標籤:      {list(truth) if truth else '(乾淨)'}")
    print(f"    規則命中:     {[f.rule_code for f in flags]}")
    print(f"    多出的規則:   {fp_types}")

print(f"\n總計 FP 案例: {fp_count}")