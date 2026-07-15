"""診斷:LLM漏抓的12個真違規,長什麼樣。"""
import json
from schema import Employee, Trade, VerdictLabel, LLMVerdict
from llm_judge import find_upcoming_news

with open("employees.json", "r", encoding="utf-8") as f:
    employees = [Employee(**e) for e in json.load(f)]
with open("trades.json", "r", encoding="utf-8") as f:
    trades = [Trade(**t) for t in json.load(f)]
with open("ground_truth.json", "r", encoding="utf-8") as f:
    ground_truth = json.load(f)
with open("llm_verdicts.json", "r", encoding="utf-8") as f:
    verdicts = {tid: LLMVerdict(**v) for tid, v in json.load(f).items()}

emp_lookup = {e.employee_id: e for e in employees}
trade_lookup = {t.trade_id: t for t in trades}

print("=" * 70)
print("被LLM漏抓的 PRE_NEWS_SUSPECT 案例(False Negatives)")
print("=" * 70)

for tid, gt in ground_truth.items():
    if "PRE_NEWS_SUSPECT" not in gt:
        continue
    t = trade_lookup[tid]
    emp = emp_lookup[t.employee_id]
    news = find_upcoming_news(t)
    
    if tid not in verdicts:
        print(f"\n[漏進LLM窗口] {tid} — {emp.name} ({emp.access_level.value})")
        print(f"    {t.side.value} {t.ticker} on {t.trade_date} qty={t.quantity}")
        if news:
            print(f"    上游新聞: {news.event_date} type={news.event_type} move={news.price_move_pct:+.1f}%")
        else:
            print(f"    上游新聞: 找不到(可能超過LOOKBACK_DAYS窗口)")
        continue
    
    v = verdicts[tid]
    if v.label == VerdictLabel.CLEAN:
        print(f"\n[LLM判CLEAN] {tid} — {emp.name} ({emp.access_level.value})")
        print(f"    {t.side.value} {t.ticker} on {t.trade_date} qty={t.quantity}")
        if news:
            print(f"    上游新聞: {news.event_date} type={news.event_type} move={news.price_move_pct:+.1f}%")
        print(f"    reasoning: {v.reasoning[:200]}...")