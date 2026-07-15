"""
streamlit_app.py — PAD Trade Monitor Reviewer Dashboard
一個給合規審查員看的極簡介面。
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from collections import Counter

from schema import Employee, Trade, LLMVerdict, VerdictLabel
from rule_engine import evaluate_all

# ------------------------------
# 頁面設定
# ------------------------------
st.set_page_config(
    page_title="PAD Trade Monitor",
    page_icon="🕵️",
    layout="wide",
)

# ------------------------------
# 資料載入(cached)
# ------------------------------
@st.cache_data
def load_data():
    with open("employees.json", "r", encoding="utf-8") as f:
        employees = [Employee(**e) for e in json.load(f)]
    with open("trades.json", "r", encoding="utf-8") as f:
        trades = [Trade(**t) for t in json.load(f)]
    with open("ground_truth.json", "r", encoding="utf-8") as f:
        ground_truth = json.load(f)
    llm_verdicts = {}
    if Path("llm_verdicts.json").exists():
        with open("llm_verdicts.json", "r", encoding="utf-8") as f:
            llm_verdicts = {tid: LLMVerdict(**v) for tid, v in json.load(f).items()}
    return employees, trades, ground_truth, llm_verdicts


employees, trades, ground_truth, llm_verdicts = load_data()
emp_lookup = {e.employee_id: e for e in employees}
trade_lookup = {t.trade_id: t for t in trades}
rule_results = evaluate_all(trades, employees)

# ------------------------------
# Header
# ------------------------------
st.title("🕵️ PAD Trade Monitor")
st.caption("Personal Account Dealing compliance review — rule engine + LLM judgment layer")

tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "🔍 Case Review", "📖 Methodology"])

# ==============================
# TAB 1: DASHBOARD
# ==============================
with tab1:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Trades", len(trades))
    col2.metric("Employees", len(employees))
    n_rule_flagged = sum(1 for f in rule_results.values() if f)
    col3.metric("Rule Engine Flags", n_rule_flagged)
    n_llm_flagged = sum(
        1 for v in llm_verdicts.values()
        if v.label in [VerdictLabel.SUSPICIOUS, VerdictLabel.REQUIRES_REVIEW]
    )
    col4.metric("LLM Reviews Flagged", n_llm_flagged)

    st.divider()

    left, right = st.columns(2)

    with left:
        st.subheader("Rule Engine — Hit Distribution")
        flag_counter = Counter()
        for flags in rule_results.values():
            for f in flags:
                flag_counter[f.rule_code] += 1
        rule_df = pd.DataFrame(
            [{"Rule": k, "Count": v} for k, v in flag_counter.most_common()]
        )
        if not rule_df.empty:
            st.bar_chart(rule_df.set_index("Rule"))

        rule_desc = {
            "PAD001": "Restricted List trade",
            "PAD002": "No pre-clearance",
            "PAD003": "Blackout period",
            "PAD004": "Covered stock conflict",
            "PAD005": "Holding period violation",
        }
        rule_df["Description"] = rule_df["Rule"].map(rule_desc)
        st.dataframe(rule_df, hide_index=True, use_container_width=True)

    with right:
        st.subheader("LLM Layer — Verdict Distribution")
        if llm_verdicts:
            label_counter = Counter(v.label.value for v in llm_verdicts.values())
            llm_df = pd.DataFrame(
                [{"Verdict": k, "Count": v} for k, v in label_counter.most_common()]
            )
            st.bar_chart(llm_df.set_index("Verdict"))
            st.dataframe(llm_df, hide_index=True, use_container_width=True)
        else:
            st.info("No LLM verdicts loaded. Run `python llm_judge.py` first.")

    st.divider()

    # 離群分析圖
    if Path("outlier_plot.png").exists():
        st.subheader("Diagnostic — LLM Verdict vs Objective Suspicion")
        st.caption(
            "Each point is one LLM-reviewed trade. Vertical axis is the LLM's verdict; "
            "horizontal axis is a heuristic 'objective suspicion' score built from "
            "MNPI access × direction consistency × time proximity. "
            "Points that cluster far from the diagonal are LLM outliers worth investigating."
        )
        # 用三欄佈局把圖限制在中間,兩邊留白
        left_gutter, img_col, right_gutter = st.columns([1, 3, 1])
        with img_col:
            st.image("outlier_plot.png", use_container_width=True)


# ==============================
# TAB 2: CASE REVIEW
# ==============================
with tab2:
    st.subheader("Individual Case Review")

    # 篩選器
    fcol1, fcol2, fcol3 = st.columns(3)
    filter_flagged = fcol1.selectbox(
        "Show",
        ["All flagged cases", "Rule engine flags only", "LLM SUSPICIOUS only",
         "LLM REQUIRES_REVIEW only", "All trades"]
    )
    filter_ticker = fcol2.selectbox(
        "Ticker",
        ["All"] + sorted(set(t.ticker for t in trades))
    )
    filter_access = fcol3.selectbox(
        "Employee access level",
        ["All", "HIGH", "MEDIUM", "LOW"]
    )

    # 建立 case 清單
    cases = []
    for t in trades:
        emp = emp_lookup[t.employee_id]
        rule_flags = rule_results.get(t.trade_id, [])
        llm_v = llm_verdicts.get(t.trade_id)

        # 篩選
        if filter_ticker != "All" and t.ticker != filter_ticker:
            continue
        if filter_access != "All" and emp.access_level.value != filter_access:
            continue

        has_rule_flag = bool(rule_flags)
        has_llm_flag = llm_v is not None and llm_v.label in [
            VerdictLabel.SUSPICIOUS, VerdictLabel.REQUIRES_REVIEW
        ]
        is_llm_susp = llm_v is not None and llm_v.label == VerdictLabel.SUSPICIOUS
        is_llm_review = llm_v is not None and llm_v.label == VerdictLabel.REQUIRES_REVIEW

        if filter_flagged == "Rule engine flags only" and not has_rule_flag:
            continue
        if filter_flagged == "LLM SUSPICIOUS only" and not is_llm_susp:
            continue
        if filter_flagged == "LLM REQUIRES_REVIEW only" and not is_llm_review:
            continue
        if filter_flagged == "All flagged cases" and not (has_rule_flag or has_llm_flag):
            continue

        cases.append({
            "trade_id": t.trade_id,
            "trade": t,
            "employee": emp,
            "rule_flags": rule_flags,
            "llm_verdict": llm_v,
        })

    st.caption(f"Showing {len(cases)} case(s)")

    if not cases:
        st.info("No cases match the current filters.")
    else:
        # 案件選單
        case_options = [
            f"{c['trade_id']} — {c['employee'].name} ({c['employee'].access_level.value}) "
            f"{c['trade'].side.value} {c['trade'].ticker} on {c['trade'].trade_date}"
            for c in cases
        ]
        selected_idx = st.selectbox(
            "Select case",
            range(len(case_options)),
            format_func=lambda i: case_options[i],
        )

        c = cases[selected_idx]
        t = c["trade"]
        emp = c["employee"]

        st.divider()

        # 案件詳情
        detail_col1, detail_col2 = st.columns(2)

        with detail_col1:
            st.markdown("### 📋 Trade Details")
            st.markdown(f"**Trade ID:** `{t.trade_id}`")
            st.markdown(f"**Ticker:** {t.ticker}")
            st.markdown(f"**Side:** {t.side.value}")
            st.markdown(f"**Quantity:** {t.quantity:,}")
            st.markdown(f"**Price:** {t.price}")
            st.markdown(f"**Trade Date:** {t.trade_date}")
            st.markdown(f"**Pre-cleared:** {'✓' if t.pre_cleared else '✗'}")
            if t.pre_clearance_id:
                st.markdown(f"**Pre-clearance ID:** `{t.pre_clearance_id}`")

        with detail_col2:
            st.markdown("### 👤 Employee")
            st.markdown(f"**Name:** {emp.name}")
            st.markdown(f"**ID:** `{emp.employee_id}`")
            st.markdown(f"**Department:** {emp.department.value}")
            st.markdown(f"**Role:** {emp.role}")

            # Access level色彩
            access_color = {
                "HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"
            }.get(emp.access_level.value, "⚪")
            st.markdown(f"**MNPI Access:** {access_color} {emp.access_level.value}")
            if emp.covered_stocks:
                st.markdown(f"**Covered stocks:** {', '.join(emp.covered_stocks)}")

        st.divider()

        # Rule engine 判斷
        st.markdown("### ⚖️ Layer 1: Rule Engine")
        if c["rule_flags"]:
            for f in c["rule_flags"]:
                sev_color = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(f.severity, "⚪")
                with st.expander(
                    f"{sev_color} {f.rule_code} — {f.rule_name} ({f.severity})",
                    expanded=True
                ):
                    st.write(f.detail)
        else:
            st.success("No hard rule violations detected.")

        # LLM judgment
        st.markdown("### 🤖 Layer 2: LLM Judgment")
        llm_v = c["llm_verdict"]
        if llm_v is None:
            st.info("This trade did not fall within the LLM review window (no relevant news event nearby).")
        else:
            verdict_style = {
                "SUSPICIOUS": ("🔴", "error"),
                "REQUIRES_REVIEW": ("🟡", "warning"),
                "CLEAN": ("🟢", "success"),
            }.get(llm_v.label.value, ("⚪", "info"))
            icon, kind = verdict_style

            getattr(st, kind)(
                f"{icon} **{llm_v.label.value}** (confidence: {llm_v.confidence:.2f})"
            )
            st.markdown("**Reasoning:**")
            st.write(llm_v.reasoning)

            if llm_v.contextual_factors:
                st.markdown("**Contextual factors:**")
                for f in llm_v.contextual_factors:
                    st.markdown(f"- {f}")


# ==============================
# TAB 3: METHODOLOGY
# ==============================
with tab3:
    st.markdown("""
    ## Two-Layer Architecture

    This system separates deterministic compliance checks from contextual judgment:

    - **Layer 1 (Rule Engine)** — five deterministic rules (PAD001–PAD005) that produce
      immediate structured output. No LLM cost, fully explainable, replayable.
    - **Layer 2 (LLM Judgment)** — DeepSeek Chat with function calling, handles
      *contextually ambiguous* pre-news trades where the same trade may be innocent
      or suspicious depending on employee MNPI access level, direction consistency
      with news, and trade size.

    ## Prompt Iteration History

    The LLM layer went through three prompt versions to converge:

    | Version | Change | True Violation F1 | Decoy Over-flag |
    |---|---|---|---|
    | v1 | Baseline framework with soft counter-example rules | 67.6% | 47.6% |
    | v2 | Upgraded counter-examples to hard decisive rules | 86.8% | 35.9% |
    | **v3** | Mandatory direction-check pre-step + tool schema warning | **84.9%** | **14.1%** |

    The v2→v3 fix addressed a specific DeepSeek failure mode: **reasoning-output
    desynchronization** — the model's chain-of-thought correctly identified the
    applicable rule, but the final `label` field in the function call output did not
    reflect it. Enforcing the direction check as the first mandatory decision point,
    plus embedding a constraint warning directly in the tool schema's
    `label.description`, resolved 85% of these cases.

    ## Decoy Traps

    The dataset contains 64 trades designed to *look suspicious* but should be judged
    CLEAN:

    - **DECOY_WRONG_DIRECTION** — HIGH access + close to news + wrong direction
    - **DECOY_LOW_ACCESS** — LOW access + perfect timing + wrong management level
    - **DECOY_SECTOR_RALLY** — trades during industry-wide rally providing alternative
      explanation

    Decoy resistance is measured separately from true-violation detection.
    A system with 100% recall but 100% over-flag rate on decoys is not usable.

    ## Known Limitations

    - **5 hard-case misses (v3):** HIGH access + direction-consistent + 1–3 days before
      news, but judged CLEAN. All five stocks also triggered other hard rules
      (Restricted List). The LLM appears to defer to the rule engine on those tickers.
    - **Distributed-small-order evasion** is not modeled.
    - **Only HK equity news** in the current implementation.

    ## Sibling Project

    See [audit-compliance-copilot](https://github.com/lochiel-huang/audit-compliance-copilot)
    for the back-office counterpart — same two-layer architecture applied to
    accounting voucher anomaly detection.
    """)