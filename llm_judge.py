"""
llm_judge.py
PAD Trade Monitor — LLM 判斷層(第二層)。

架構理念(mirror audit-compliance-copilot v3):
- 規則引擎:決定性、抓硬規則
- LLM 層:處理「時間相關性」與「情境曖昧」案例
  → 聚焦目標:PRE_NEWS_SUSPECT(新聞前異常交易)

Prompt 教訓(來自 audit-compliance-copilot v1→v3):
- v1: prompt 太寬鬆 → alert fatigue
- v2: 加太多負面例子 → over-suppression
- v3(本檔採用): 明確判斷框架 + 反例規則 + 結構化輸出
"""

import os
import json
from typing import List, Optional
from openai import OpenAI
from dotenv import load_dotenv
from schema import Trade, Employee, NewsEvent, LLMVerdict, VerdictLabel
from data_generator import NEWS_EVENTS

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    raise ValueError(
        "未找到 DEEPSEEK_API_KEY。請在 .env 檔案中設定,格式:\n"
        "DEEPSEEK_API_KEY=sk-xxxxx"
    )

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

MODEL = "deepseek-chat"
LOOKBACK_DAYS = 7  # 檢查新聞前 N 天內的交易(對應 generator 的注入分布 1-7)


# ------------------------------
# 情境準備
# ------------------------------

def find_upcoming_news(trade: Trade, lookback_days: int = LOOKBACK_DAYS) -> Optional[NewsEvent]:
    """若該交易日之後 N 天內該股有新聞事件,則回傳該事件。"""
    for event in NEWS_EVENTS:
        if event.ticker != trade.ticker:
            continue
        days_ahead = (event.event_date - trade.trade_date).days
        if 0 < days_ahead <= lookback_days:
            return event
    return None


# ------------------------------
# Prompt(v3 版本)
# ------------------------------

SYSTEM_PROMPT = """你是一位金融合規審查員,專門評估員工個人交易(Personal Account Dealing, PAD)是否構成「新聞前異常交易」(pre-news trading)嫌疑。

# 判斷框架
評估以下五個維度,綜合判斷:

1. **時間接近度**:交易距新聞日
   - 1-2 天:高度可疑
   - 3-5 天:中度可疑
   - 6 天以上:顯著降低

2. **員工 MNPI 接觸層級**
   - HIGH(IB deal team、senior research):高風險
   - MEDIUM(analyst、PM):中風險
   - LOW(compliance、back office):低風險

3. **方向一致性(決定性維度)**
   - 利多新聞前買入 / 利空前賣出 → 方向一致(疑度加重)
   - 利多前賣出 / 利空前買入 → 方向不一致(疑度顯著降低,幾乎排除典型 pre-news trading)

4. **交易規模**
   - 明顯高於該員工日常水準 → 加重可疑度
   - 常規規模 → 中性

5. **替代解釋**
   - 產業普遍上漲、大盤趨勢、公開分析師報告 → 降低可疑度

# 決定性規則(必須遵守,不可以綜合判斷覆蓋)

# 強制檢查步驟(必須第一步執行)

在應用任何規則之前,先做「方向檢查」:
STEP 1: 判斷新聞方向 — price_move_pct > 0 是 BULL,< 0 是 BEAR
STEP 2: 判斷交易方向與新聞方向是否一致
  - BUY + BULL = 一致
  - SELL + BEAR = 一致
  - BUY + BEAR = 不一致
  - SELL + BULL = 不一致
STEP 3: 若不一致 → 立即決定 label = "CLEAN" 或 "REQUIRES_REVIEW",跳過規則 C、D 的評估
STEP 4: 若一致 → 才繼續評估規則 B、C、D

⚠️ 不允許先評估規則 C 然後才回頭「因為規則 A 而降級」——這種順序容易在最終 label 出錯。
方向檢查必須是第一個決策點。

## 規則 A(方向不一致→強制降級)
若交易方向與新聞方向不一致(利多前賣出 / 利空前買入),
最終結論**不可為 SUSPICIOUS**,最多只能是 REQUIRES_REVIEW 或 CLEAN。
理由:方向相反意味著若真有 MNPI,員工做的是虧損操作,不符合典型 pre-news trading 動機。
複雜情境(如反向對沖)必須有明確衍生品或關聯帳戶證據,否則不足以覆蓋規則 A。

## 規則 B(LOW access→強制降級)
LOW MNPI access 員工(compliance、back office)缺乏 MNPI 接觸管道,
最終結論**不可為 SUSPICIOUS**,最多只能是 REQUIRES_REVIEW。
即使時間接近、方向一致、大額,LOW access 依然是決定性減輕因素。

## 規則 C(果斷 SUSPICIOUS)
以下情境**必須**判 SUSPICIOUS,不可退為 REQUIRES_REVIEW:
- HIGH access + 方向一致 + 距新聞 ≤ 3 天
- MEDIUM access + 方向一致 + 距新聞 ≤ 2 天 + 交易規模明顯偏大

## 規則 D(至少 REQUIRES_REVIEW)
HIGH access + 方向一致 + 距新聞 4-5 天 → 至少 REQUIRES_REVIEW,不判 CLEAN。

# 輸出標籤定義
- CLEAN:綜合證據明確無嫌疑
- SUSPICIOUS:多維度指標明確可疑,建議進一步調查
- REQUIRES_REVIEW:曖昧案例,需人工深查

# 輸出要求
請透過 submit_verdict 函式提交結構化判斷,並在 reasoning 中明確引用觸發的規則。
例如:「觸發規則 A(方向不一致),降級為 CLEAN」或「觸發規則 C(HIGH+一致+3天),判 SUSPICIOUS」。
"""

def build_user_prompt(trade: Trade, employee: Employee, news: NewsEvent) -> str:
    days_before = (news.event_date - trade.trade_date).days
    return f"""請評估以下員工交易:

## 員工資料
- ID: {employee.employee_id}
- 姓名: {employee.name}
- 部門: {employee.department.value}
- 職位: {employee.role}
- MNPI 接觸層級: {employee.access_level.value}
- 覆蓋股票: {employee.covered_stocks if employee.covered_stocks else '(無)'}

## 交易資料
- 交易 ID: {trade.trade_id}
- 標的: {trade.ticker}
- 方向: {trade.side.value}
- 數量: {trade.quantity}
- 交易日: {trade.trade_date}
- 成交價: {trade.price}
- 已預先申報: {trade.pre_cleared}

## 後續新聞事件
- 新聞日: {news.event_date}(交易後 {days_before} 天)
- 事件類型: {news.event_type}
- 標題: {news.headline}
- 當日股價變動: {news.price_move_pct:+.1f}%

依框架判斷此交易是否構成 pre-news trading 嫌疑,並透過 submit_verdict 提交。
"""


# ------------------------------
# Function calling schema
# ------------------------------

VERDICT_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_verdict",
        "description": "提交 PAD 合規審查結論",
        "parameters": {
            "type": "object",
            "properties": {
              "label": {
                    "type": "string",
                    "enum": ["CLEAN", "SUSPICIOUS", "REQUIRES_REVIEW"],
                    "description": "審查結論。⚠️ 若交易方向與新聞方向不一致(BUY+BEAR 或 SELL+BULL),此欄位絕對不可為 'SUSPICIOUS',必須為 'CLEAN' 或 'REQUIRES_REVIEW'"
                },
                "confidence": {
                    "type": "number",
                    "description": "0-1 之間,對此結論的信心",
                    "minimum": 0.0,
                    "maximum": 1.0
                },
                "reasoning": {
                    "type": "string",
                    "description": "2-4 句解釋,說明得到此結論的關鍵原因"
                },
                "contextual_factors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "影響判斷的具體因素列表"
                }
            },
            "required": ["label", "confidence", "reasoning", "contextual_factors"]
        }
    }
}


def judge_trade(trade: Trade, employee: Employee, news: NewsEvent) -> LLMVerdict:
    """呼叫 LLM,強制以 function calling 回傳結構化 verdict。"""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(trade, employee, news)}
        ],
        tools=[VERDICT_TOOL],
        tool_choice={"type": "function", "function": {"name": "submit_verdict"}},
        temperature=0.2
    )

    tool_call = response.choices[0].message.tool_calls[0]
    args = json.loads(tool_call.function.arguments)

    return LLMVerdict(
        label=VerdictLabel(args["label"]),
        confidence=float(args["confidence"]),
        reasoning=args["reasoning"],
        contextual_factors=args["contextual_factors"]
    )


# ------------------------------
# 主管線
# ------------------------------

def review_with_llm(trades: List[Trade], employees: List[Employee]):
    emp_lookup = {e.employee_id: e for e in employees}
    verdicts = {}
    to_review = []
    for t in trades:
        news = find_upcoming_news(t)
        if news is not None:
            to_review.append((t, news))

    print(f"共 {len(to_review)} 筆交易落在新聞前 {LOOKBACK_DAYS} 天窗口,交付 LLM 審查\n")

    for i, (t, news) in enumerate(to_review, 1):
        emp = emp_lookup.get(t.employee_id)
        if emp is None:
            continue
        print(f"[{i}/{len(to_review)}] {t.trade_id} — {emp.name} "
              f"({emp.access_level.value}) {t.side.value} {t.ticker} on {t.trade_date} "
              f"→ news in {(news.event_date - t.trade_date).days} days")
        try:
            v = judge_trade(t, emp, news)
            verdicts[t.trade_id] = v
            print(f"    verdict: {v.label.value} (conf={v.confidence:.2f})")
            print(f"    reasoning: {v.reasoning}")
        except Exception as e:
            print(f"    ✗ 失敗: {e}")
    return verdicts


# ------------------------------
# 主程式
# ------------------------------

if __name__ == "__main__":
    with open("employees.json", "r", encoding="utf-8") as f:
        employees = [Employee(**e) for e in json.load(f)]
    with open("trades.json", "r", encoding="utf-8") as f:
        trades = [Trade(**t) for t in json.load(f)]
    with open("ground_truth.json", "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    verdicts = review_with_llm(trades, employees)

    with open("llm_verdicts.json", "w", encoding="utf-8") as f:
        json.dump(
            {tid: v.model_dump(mode="json") for tid, v in verdicts.items()},
            f, ensure_ascii=False, indent=2
        )

    # ==========================================================
    # 三層評估:真違規 / 誘惑陷阱 / 曖昧邊界
    # ==========================================================
    DECOY_TYPES = {"DECOY_WRONG_DIRECTION", "DECOY_LOW_ACCESS", "DECOY_SECTOR_RALLY"}
    reviewed_ids = set(verdicts.keys())

    # --- 1. 真違規 evaluation(PRE_NEWS_SUSPECT)---
    tp = fp = fn = 0
    decoy_review_flagged_as_true_violation = 0  # LLM把decoy誤判成真違規

    for tid, v in verdicts.items():
        gt = set(ground_truth.get(tid, []))
        is_true_violation = "PRE_NEWS_SUSPECT" in gt
        is_decoy = bool(gt & DECOY_TYPES)
        llm_flag_suspicious = v.label == VerdictLabel.SUSPICIOUS
        llm_flag_any = v.label in [VerdictLabel.SUSPICIOUS, VerdictLabel.REQUIRES_REVIEW]

        # 真違規指標:只算「非decoy」的案例
        if not is_decoy:
            if llm_flag_any and is_true_violation:
                tp += 1
            elif llm_flag_any and not is_true_violation:
                fp += 1
            elif not llm_flag_any and is_true_violation:
                fn += 1

    # 真違規但根本沒進LLM窗口
    for tid, gt_list in ground_truth.items():
        if "PRE_NEWS_SUSPECT" in gt_list and tid not in reviewed_ids:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0

    print("\n" + "=" * 60)
    print("【1】 真違規評估(PRE_NEWS_SUSPECT,排除誘惑陷阱)")
    print("=" * 60)
    print(f"True Positives:  {tp}")
    print(f"False Positives: {fp}")
    print(f"False Negatives: {fn}")
    print(f"Precision: {precision:.2%}")
    print(f"Recall:    {recall:.2%}")
    print(f"F1 Score:  {f1:.2%}")

    # --- 2. 誘惑陷阱 evaluation ---
    decoy_stats = {dt: {"total": 0, "suspicious": 0, "requires_review": 0, "clean": 0}
                   for dt in DECOY_TYPES}

    for tid, v in verdicts.items():
        gt = set(ground_truth.get(tid, []))
        decoy_type = next((dt for dt in DECOY_TYPES if dt in gt), None)
        if decoy_type is None:
            continue
        decoy_stats[decoy_type]["total"] += 1
        if v.label == VerdictLabel.SUSPICIOUS:
            decoy_stats[decoy_type]["suspicious"] += 1
        elif v.label == VerdictLabel.REQUIRES_REVIEW:
            decoy_stats[decoy_type]["requires_review"] += 1
        else:
            decoy_stats[decoy_type]["clean"] += 1

    print("\n" + "=" * 60)
    print("【2】 誘惑陷阱抗性評估(理想:SUSPICIOUS ↓, CLEAN ↑)")
    print("=" * 60)
    total_decoys_reviewed = 0
    total_over_flagged = 0
    total_correct_clean = 0
    for dt, s in decoy_stats.items():
        if s["total"] == 0:
            print(f"\n{dt}: (未進入LLM審查窗口)")
            continue
        over_flag = s["suspicious"] / s["total"]
        correct_clean = s["clean"] / s["total"]
        total_decoys_reviewed += s["total"]
        total_over_flagged += s["suspicious"]
        total_correct_clean += s["clean"]
        print(f"\n{dt}: {s['total']} 筆進入LLM審查")
        print(f"  SUSPICIOUS (過度警報)  {s['suspicious']:3d}  ({over_flag:.1%})")
        print(f"  REQUIRES_REVIEW        {s['requires_review']:3d}")
        print(f"  CLEAN (正確識別)       {s['clean']:3d}  ({correct_clean:.1%})")

    if total_decoys_reviewed > 0:
        print(f"\n總計誘惑陷阱: {total_decoys_reviewed} 筆進入LLM審查")
        print(f"整體 over-flag rate:    {total_over_flagged/total_decoys_reviewed:.1%}")
        print(f"整體 correct-clean rate: {total_correct_clean/total_decoys_reviewed:.1%}")

    # --- 3. 決策分布總覽 ---
    from collections import Counter
    label_dist = Counter(v.label.value for v in verdicts.values())
    print("\n" + "=" * 60)
    print(f"【3】 LLM 整體決策分布(共 {len(verdicts)} 筆審查)")
    print("=" * 60)
    for label, count in label_dist.most_common():
        print(f"  {label:20s} {count}")