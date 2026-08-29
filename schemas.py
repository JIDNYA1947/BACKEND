"""
Pydantic models for request validation and response serialization.
"""
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Feature 10 / 12 - Scheme matching & eligibility explanation
# ---------------------------------------------------------------------------

class BusinessProfile(BaseModel):
    """Input profile used for deterministic scheme matching."""

    business_type: str = Field(..., min_length=1, examples=["Food Processing"])
    project_cost: float = Field(..., ge=0, examples=[800000])
    location: str = Field(..., min_length=1, examples=["Rural"])
    category: str = Field(..., min_length=1, examples=["Eligible Category"])

    @field_validator("business_type", "location", "category")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v.strip()


class ConditionResult(BaseModel):
    condition: str
    passed: bool


class SchemeMatchResult(BaseModel):
    scheme_id: str
    scheme_name: str
    passed: bool
    score: float
    conditions: List[ConditionResult]
    disclaimer: str


class SchemeMatchResponse(BaseModel):
    profile: BusinessProfile
    results: List[SchemeMatchResult]
    matched_scheme_ids: List[str]
    mandatory_disclaimer: str


class ExplanationCondition(BaseModel):
    condition: str
    passed: bool
    actual: Optional[str] = None
    expected: Optional[str] = None


class SchemeExplanation(BaseModel):
    scheme_id: str
    scheme_name: str
    passed: bool
    score: float
    conditions: List[ExplanationCondition]
    disclaimer: str


class SchemeExplanationResponse(BaseModel):
    profile: BusinessProfile
    explanations: List[SchemeExplanation]
    mandatory_disclaimer: str


class SchemeInfo(BaseModel):
    scheme_id: str
    scheme_name: str
    description: str
    criteria: dict
    disclaimer: str


class SchemeListResponse(BaseModel):
    schemes: List[SchemeInfo]
    note: str


# ---------------------------------------------------------------------------
# Feature 9 - Post-loan health check
# ---------------------------------------------------------------------------

class LoanCreate(BaseModel):
    loan_id: Optional[str] = Field(None, description="Optional. Auto-generated if omitted.")
    user_id: str = Field(..., min_length=1)
    phone_number: str = Field(..., min_length=6, description="E.164 style, e.g. +919999999999")
    business_name: str = Field(..., min_length=1)
    loan_amount: float = Field(..., gt=0)

    @field_validator("phone_number")
    @classmethod
    def phone_looks_valid(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned.startswith("+") or not cleaned[1:].replace(" ", "").isdigit():
            raise ValueError("phone_number must be in international format, e.g. +919999999999")
        return cleaned


class LoanOut(BaseModel):
    loan_id: str
    user_id: str
    phone_number: str
    business_name: str
    loan_amount: float
    created_at: str


class SurveySendResponse(BaseModel):
    loan_id: str
    status: str
    demo_mode: bool
    message_preview: str
    sent_at: str


class SurveyResponseIn(BaseModel):
    """
    Raw WhatsApp-style reply. Accepts free text such as:
    'GOOD, ON_TIME, NO'
    Case-insensitive, comma or whitespace separated.
    """
    loan_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


class SurveyResponseOut(BaseModel):
    loan_id: str
    sales_status: str
    emi_status: str
    issue_status: str
    concerning_count: int
    alert_created: bool
    created_at: str


class MentorAlertOut(BaseModel):
    id: int
    loan_id: str
    reason: str
    created_at: str
    resolved: bool


class MentorAlertListResponse(BaseModel):
    alerts: List[MentorAlertOut]
    count: int


class HealthResponse(BaseModel):
    status: str
    demo_mode: bool
    survey_interval_minutes: int
