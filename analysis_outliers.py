"""
analysis_outliers.py
把 llm_verdicts.json + ground_truth.json 畫成離群散點圖。
每次改完 prompt 重跑 llm_judge.py 之後,跑這個看 outlier 有沒有變少。
"""
import json
import random
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse

NEWS_DIRECTION = {
    "0388.HK": "BEAR", "0027.HK": "BEAR",
    "1211.HK": "BULL", "1810.HK": "BULL",
    "0175.HK": "BULL", "3690.HK": "BULL",
}
ACCESS_W = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.2}
VERDICT_SCORE = {"SUSPICIOUS": 1.0, "REQUIRES_REVIEW": 0.5, "CLEAN": 0.0}

with open("employees.json", "r", encoding="utf-8") as f:
    employees = {e["employee_id"]: e for e in json.load(f)}
with open("trades.json", "r", encoding="utf-8") as f:
    trades = {t["trade_id"]: t for t in json.load(f)}
with open("ground_truth.json", "r", encoding="utf-8") as f:
    gt = json.load(f)
with open("llm_verdicts.json", "r", encoding="utf-8") as f:
    verdicts = json.load(f)

from datetime import date
def parse_date(s): return date.fromisoformat(s)

# 讀 llm_judge 裡的 NEWS_EVENTS 找出對應新聞天數
from data_generator import NEWS_EVENTS
def find_days_before(t):
    for e in NEWS_EVENTS:
        if e.ticker == t["ticker"]:
            d = (e.event_date - parse_date(t["trade_date"])).days
            if 0 < d <= 7:
                return d
    return None

records = []
for tid, v in verdicts.items():
    t = trades[tid]
    emp = employees[t["employee_id"]]
    access = emp["access_level"]
    side = t["side"]
    ticker = t["ticker"]
    news_dir = NEWS_DIRECTION.get(ticker, "?")
    days = find_days_before(t)
    if days is None:
        continue
    direction_consistent = (side == "BUY" and news_dir == "BULL") or \
                           (side == "SELL" and news_dir == "BEAR")
    time_prox = (8 - days) / 7.0
    dir_signal = 1.0 if direction_consistent else -0.3
    objective = ACCESS_W[access] * dir_signal * time_prox
    llm = VERDICT_SCORE[v["label"]]
    truth = gt.get(tid, [])
    is_decoy_wrong = "DECOY_WRONG_DIRECTION" in truth
    is_decoy_low = "DECOY_LOW_ACCESS" in truth
    is_true_vio = "PRE_NEWS_SUSPECT" in truth
    if is_decoy_wrong:
        cat = "DECOY: Wrong Direction (should be CLEAN)"
    elif is_decoy_low:
        cat = "DECOY: Low Access (should be CLEAN)"
    elif is_true_vio:
        cat = "True Violation (should be SUSPICIOUS)"
    else:
        cat = "Other"
    records.append({"objective": objective, "llm": llm, "category": cat})

print(f"Analyzed {len(records)} LLM-reviewed trades")

colors = {
    "DECOY: Wrong Direction (should be CLEAN)": "#d62728",
    "DECOY: Low Access (should be CLEAN)": "#2ca02c",
    "True Violation (should be SUSPICIOUS)": "#1f77b4",
    "Other": "#bbbbbb",
}
markers = {
    "DECOY: Wrong Direction (should be CLEAN)": "X",
    "DECOY: Low Access (should be CLEAN)": "o",
    "True Violation (should be SUSPICIOUS)": "^",
    "Other": ".",
}

random.seed(42)
fig, ax = plt.subplots(figsize=(12, 8))
for cat, color in colors.items():
    xs = [r["objective"] + random.uniform(-0.02, 0.02) for r in records if r["category"] == cat]
    ys = [r["llm"] + random.uniform(-0.04, 0.04) for r in records if r["category"] == cat]
    if xs:
        ax.scatter(xs, ys, c=color, marker=markers[cat],
                   s=90, alpha=0.7, edgecolors="black", linewidth=0.5,
                   label=f"{cat} (n={len(xs)})")

for y in [0.0, 0.5, 1.0]:
    ax.axhline(y, color="#999", linestyle=":", alpha=0.4, linewidth=0.8)

outlier_zone = Ellipse((-0.15, 0.95), width=0.5, height=0.25, angle=0,
                        edgecolor="red", facecolor="none",
                        linewidth=2, linestyle="--", alpha=0.7)
ax.add_patch(outlier_zone)
ax.annotate("Over-flagging outliers", xy=(-0.15, 0.95), xytext=(-0.7, 1.15),
            fontsize=10, color="red", fontweight="bold",
            arrowprops=dict(arrowstyle="->", color="red", alpha=0.6))

ax.set_yticks([0.0, 0.5, 1.0])
ax.set_yticklabels(["CLEAN", "REQUIRES_REVIEW", "SUSPICIOUS"], fontsize=11)
ax.set_ylim(-0.2, 1.4)
ax.set_xlabel("Objective Suspicion Score", fontsize=11)
ax.set_ylabel("LLM Verdict", fontsize=11)
ax.set_title("PAD Trade Monitor — LLM Verdict vs Objective Suspicion", fontsize=13)
ax.legend(loc="lower right", fontsize=9)
ax.grid(alpha=0.2)
plt.tight_layout()
plt.savefig("outlier_plot.png", dpi=150, bbox_inches="tight")
print("Saved outlier_plot.png")