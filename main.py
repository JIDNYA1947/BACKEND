"""
FastAPI application entrypoint.

Wires together:
- Feature 10/12: deterministic scheme matching + eligibility explanation
- Feature 9: post-loan WhatsApp business health checks + mentor alerts

Swagger UI is available at /docs (default FastAPI behaviour).
"""
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db, get_connection, utcnow_iso
from app import rules, health_checks, scheduler
from app.schemas import (
    BusinessProfile,
    SchemeMatchResponse,
    SchemeMatchResult,
    ConditionResult,
    SchemeExplanationResponse,
    SchemeExplanation,
    ExplanationCondition,
    SchemeListResponse,
    SchemeInfo,
    LoanCreate,
    LoanOut,
    SurveySendResponse,
    SurveyResponseIn,
    SurveyResponseOut,
    MentorAlertOut,
    MentorAlertListResponse,
    HealthResponse,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    try:
        init_db()
        logger.info("Database initialized at %s", settings.DATABASE_PATH)
    except Exception:
        logger.exception("Database initialization failed")
        raise

    try:
        scheduler.start_scheduler()
    except Exception:
        # The API must still work even if the scheduler fails to start.
        logger.exception("Scheduler failed to start - periodic surveys will be unavailable.")

    yield

    # --- shutdown ---
    scheduler.shutdown_scheduler()


app = FastAPI(
    title="Schemes & Integrations Backend",
    description=(
        "Deterministic government scheme matching + post-loan WhatsApp "
        "business health checks for a hackathon MSME lending assistant."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health():
    return HealthResponse(
        status="ok",
        demo_mode=settings.DEMO_MODE,
        survey_interval_minutes=settings.SURVEY_INTERVAL_MINUTES,
    )


# ---------------------------------------------------------------------------
# Feature 10 / 12 - Scheme matching & explanation
# ---------------------------------------------------------------------------

@app.get("/api/schemes", response_model=SchemeListResponse, tags=["Schemes"])
def list_schemes():
    try:
        raw = rules.load_schemes_raw()
    except rules.SchemeDataError as e:
        raise HTTPException(status_code=500, detail=str(e))

    schemes = [
        SchemeInfo(
            scheme_id=s["scheme_id"],
            scheme_name=s["scheme_name"],
            description=s.get("description", ""),
            criteria=s.get("criteria", {}),
            disclaimer=s.get("disclaimer", settings.MANDATORY_DISCLAIMER),
        )
        for s in raw["schemes"]
    ]
    note = raw.get("_meta", {}).get(
        "note",
        "Demo/configurable criteria only - not an authoritative source of government rules.",
    )
    return SchemeListResponse(schemes=schemes, note=note)


@app.post("/api/schemes/match", response_model=SchemeMatchResponse, tags=["Schemes"])
def match_schemes(profile: BusinessProfile):
    try:
        raw_results = rules.match_schemes(profile.model_dump())
    except rules.SchemeDataError as e:
        raise HTTPException(status_code=500, detail=str(e))

    results = [
        SchemeMatchResult(
            scheme_id=r["scheme_id"],
            scheme_name=r["scheme_name"],
            passed=r["passed"],
            score=r["score"],
            conditions=[ConditionResult(condition=c["condition"], passed=c["passed"]) for c in r["conditions"]],
            disclaimer=r["disclaimer"],
        )
        for r in raw_results
    ]
    matched_ids = [r.scheme_id for r in results if r.passed]

    return SchemeMatchResponse(
        profile=profile,
        results=results,
        matched_scheme_ids=matched_ids,
        mandatory_disclaimer=settings.MANDATORY_DISCLAIMER,
    )


@app.post("/api/schemes/explain", response_model=SchemeExplanationResponse, tags=["Schemes"])
def explain_schemes(profile: BusinessProfile):
    """
    Reuses the exact same deterministic engine as /api/schemes/match.
    Returns condition-by-condition results with actual vs expected values,
    suitable for direct frontend display or for an AI/RAG layer to turn
    into a natural-language explanation (the AI must not change the result).
    """
    try:
        raw_results = rules.explain_schemes(profile.model_dump())
    except rules.SchemeDataError as e:
        raise HTTPException(status_code=500, detail=str(e))

    explanations = [
        SchemeExplanation(
            scheme_id=r["scheme_id"],
            scheme_name=r["scheme_name"],
            passed=r["passed"],
            score=r["score"],
            conditions=[
                ExplanationCondition(
                    condition=c["condition"],
                    passed=c["passed"],
                    actual=c.get("actual"),
                    expected=c.get("expected"),
                )
                for c in r["conditions"]
            ],
            disclaimer=r["disclaimer"],
        )
        for r in raw_results
    ]

    return SchemeExplanationResponse(
        profile=profile,
        explanations=explanations,
        mandatory_disclaimer=settings.MANDATORY_DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# Feature 9 - Loans & post-loan health checks
# ---------------------------------------------------------------------------

@app.post("/api/loans", response_model=LoanOut, status_code=201, tags=["Loans & Health Checks"])
def create_loan(loan: LoanCreate):
    loan_id = loan.loan_id or f"LOAN-{uuid.uuid4().hex[:10].upper()}"
    created_at = utcnow_iso()

    try:
        with get_connection() as conn:
            existing = conn.execute("SELECT 1 FROM loans WHERE loan_id = ?", (loan_id,)).fetchone()
            if existing:
                raise HTTPException(status_code=409, detail=f"Loan '{loan_id}' already exists")
            conn.execute(
                """INSERT INTO loans (loan_id, user_id, phone_number, business_name, loan_amount, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (loan_id, loan.user_id, loan.phone_number, loan.business_name, loan.loan_amount, created_at),
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error while creating loan: {e}")

    return LoanOut(
        loan_id=loan_id,
        user_id=loan.user_id,
        phone_number=loan.phone_number,
        business_name=loan.business_name,
        loan_amount=loan.loan_amount,
        created_at=created_at,
    )


@app.get("/api/loans/{loan_id}", response_model=LoanOut, tags=["Loans & Health Checks"])
def get_loan(loan_id: str):
    loan = health_checks.get_loan(loan_id)
    if loan is None:
        raise HTTPException(status_code=404, detail=f"Loan '{loan_id}' not found")
    return LoanOut(**loan)


@app.post(
    "/api/health-checks/send/{loan_id}",
    response_model=SurveySendResponse,
    tags=["Loans & Health Checks"],
)
def send_health_check(loan_id: str):
    try:
        result = health_checks.send_survey(loan_id)
    except health_checks.LoanNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send survey: {e}")
    return SurveySendResponse(**result)


@app.post(
    "/api/health-checks/respond",
    response_model=SurveyResponseOut,
    tags=["Loans & Health Checks"],
)
def respond_health_check(payload: SurveyResponseIn):
    try:
        result = health_checks.record_response(payload.loan_id, payload.message)
    except health_checks.LoanNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except health_checks.MalformedSurveyResponseError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record survey response: {e}")
    return SurveyResponseOut(**result)


@app.get("/api/alerts", response_model=MentorAlertListResponse, tags=["Loans & Health Checks"])
def get_alerts(resolved: Optional[bool] = Query(None, description="Filter by resolved status")):
    try:
        rows = health_checks.list_alerts(resolved=resolved)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch alerts: {e}")

    alerts = [
        MentorAlertOut(
            id=r["id"],
            loan_id=r["loan_id"],
            reason=r["reason"],
            created_at=r["created_at"],
            resolved=bool(r["resolved"]),
        )
        for r in rows
    ]
    return MentorAlertListResponse(alerts=alerts, count=len(alerts))


@app.patch("/api/alerts/{alert_id}/resolve", response_model=MentorAlertOut, tags=["Loans & Health Checks"])
def resolve_alert(alert_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM mentor_alerts WHERE id = ?", (alert_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")
        conn.execute("UPDATE mentor_alerts SET resolved = 1 WHERE id = ?", (alert_id,))
        updated = conn.execute("SELECT * FROM mentor_alerts WHERE id = ?", (alert_id,)).fetchone()

    return MentorAlertOut(
        id=updated["id"],
        loan_id=updated["loan_id"],
        reason=updated["reason"],
        created_at=updated["created_at"],
        resolved=bool(updated["resolved"]),
    )
