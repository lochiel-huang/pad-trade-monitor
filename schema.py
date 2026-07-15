"""
schema.py
PAD Trade Monitor — Personal Account Dealing 合規審查資料模型

架構理念與 audit-compliance-copilot 對稱:
- 該項目建模的是「憑證+分錄+附件」
- 本項目建模的是「員工+交易+價格/新聞情境」
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Literal, Optional
from datetime import date, time
from enum import Enum


# ------------------------------
# 受控詞彙 (Enums)
# ------------------------------

class Department(str, Enum):
    RESEARCH = "Research"
    INVESTMENT_BANKING = "Investment Banking"
    ASSET_MANAGEMENT = "Asset Management"
    SALES_TRADING = "Sales & Trading"
    COMPLIANCE = "Compliance"
    BACK_OFFICE = "Back Office"


class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class AccessLevel(str, Enum):
    """MNPI (Material Non-Public Information) 接觸層級"""
    HIGH = "HIGH"       # IB deal team、senior research
    MEDIUM = "MEDIUM"   # covering analyst
    LOW = "LOW"         # back office、support


class RestrictionReason(str, Enum):
    DEAL = "Deal-related"
    RESEARCH_COVERAGE = "Research coverage"
    INSIDER_INFO = "Access to insider info"
    OTHER = "Other"


class VerdictLabel(str, Enum):
    CLEAN = "CLEAN"
    SUSPICIOUS = "SUSPICIOUS"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


# ------------------------------
# 核心實體
# ------------------------------

class Employee(BaseModel):
    """員工檔案 — 決定該員工能碰哪些股票、有多少MNPI風險。"""
    employee_id: str = Field(..., description="e.g. EMP0001")
    name: str
    department: Department
    role: str = Field(..., description="e.g. Analyst, VP, MD")
    access_level: AccessLevel
    covered_stocks: List[str] = Field(
        default_factory=list,
        description="分析師所覆蓋的個股,原則上不得自行交易"
    )
    hire_date: date


class RestrictedListEntry(BaseModel):
    """限制交易清單條目 — 全公司或部門級。"""
    ticker: str
    restriction_start: date
    restriction_end: date
    reason: RestrictionReason
    applies_to_department: Optional[Department] = None  # None = firm-wide


class NewsEvent(BaseModel):
    """公司重大新聞事件 — LLM層用來判斷「交易時點是否可疑」。"""
    ticker: str
    event_date: date
    event_type: str = Field(..., description="earnings / M&A / profit_warning / ...")
    headline: str
    price_move_pct: float = Field(..., description="事件當日股價變動 %")


class Trade(BaseModel):
    """單筆員工個人帳戶交易。"""
    trade_id: str
    employee_id: str
    ticker: str
    side: TradeSide
    quantity: int = Field(..., gt=0)
    trade_date: date
    trade_time: time
    price: float = Field(..., gt=0)
    pre_cleared: bool = False
    pre_clearance_id: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def check_preclearance_consistency(self):
        """若聲稱已預先核准,則必須提供核准編號。"""
        if self.pre_cleared and not self.pre_clearance_id:
            raise ValueError("pre_cleared=True 但 pre_clearance_id 未提供")
        return self


# ------------------------------
# 審查輸出 (Verdict)
# ------------------------------

class RuleFlag(BaseModel):
    """規則引擎命中的單條違規。"""
    rule_code: str = Field(..., description="e.g. PAD001, PAD002")
    rule_name: str
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    detail: str


class LLMVerdict(BaseModel):
    """LLM判斷層對曖昧案例的結構化輸出。"""
    label: VerdictLabel
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    contextual_factors: List[str] = Field(
        default_factory=list,
        description="e.g. '交易在盈利預告前3天'、'產業普遍上漲'"
    )


class ReviewVerdict(BaseModel):
    """完整審查管線對單筆交易的最終輸出。"""
    trade_id: str
    rule_flags: List[RuleFlag] = Field(default_factory=list)
    llm_verdict: Optional[LLMVerdict] = None
    final_label: VerdictLabel
    reviewer_action: Optional[str] = None  # human-in-the-loop