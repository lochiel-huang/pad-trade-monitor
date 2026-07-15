"""診斷:v3被漏抓的PRE_NEWS_SUSPECT — 是不是資料生成本身矛盾。"""
import json
from schema import Employee, Trade, VerdictLabel, LLMVerdict
from llm_judge import find_upcoming_news

with open("employees.json", "r", encoding="utf-8") as f:
    employees = {e["employee_id"]: Employee(**e) for e in json.load(f)}
with open("trades.json", "r", encoding="utf-8") as f:
    trades = {t["trade_id"]: Trade(**t) for t in json.load(f)}
with open("ground_truth.json", "r", encoding="utf-8") as f:
    ground_truth = json.load(f)
with open("llm_verdicts.json", "r", encoding="utf-8") as f:
    verdicts = {tid: LLMVerdict(**v) for tid, v in json.load(f).items()}

NEWS_DIR = {"0388.HK": "BEAR", "0027.HK": "BEAR",
            "1211.HK": "BULL", "1810.HK": "BULL",
            "0175.HK": "BULL", "3690.HK": "BULL"}

print("=" * 70)
print("被漏抓的 PRE_NEWS_SUSPECT — 檢查方向一致性")
print("=" * 70)

for tid, gt in ground_truth.items():
    if "PRE_NEWS_SUSPECT" not in gt:
        continue
    if tid not in verdicts:
        continue
    v = verdicts[tid]
    if v.label != VerdictLabel.CLEAN:
        continue
    t = trades[tid]
    emp = employees[t.employee_id]
    news = find_upcoming_news(t)
    news_direction = NEWS_DIR.get(t.ticker, "?")
    direction_consistent = (
        (t.side.value == "BUY" and news_direction == "BULL")
        or (t.side.value == "SELL" and news_direction == "BEAR")
    )
    print(f"\n[{tid}] {emp.name} ({emp.access_level.value})")
    print(f"  {t.side.value} {t.ticker} on {t.trade_date} qty={t.quantity}")
    print(f"  新聞方向: {news_direction} ({news.event_type if news else '?'})")
    print(f"  方向一致: {'✓' if direction_consistent else '✗ 矛盾!'}")
    print(f"  LLM verdict: {v.label.value}")