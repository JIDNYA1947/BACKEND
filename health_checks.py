"""
Post-loan business health check logic (Feature 9).

Handles:
- sending the 3-question WhatsApp survey to a loan's registered phone number
- parsing free-text survey replies (e.g. "GOOD, ON_TIME, NO")
- counting "concerning" answers
- raising a mentor alert when the concerning-answer threshold is met
"""
import re
from typing import Optional

from app.config import settings
from app.database import get_connection, utcnow_iso
from app import whatsapp

CONCERNING_SALES = {"FALLING", "DOWN", "DECLINING", "POOR", "BAD"}
CONCERNING_EMI = {"MISSED", "LATE", "OVERDUE", "DELAYED", "DEFAULT"}
CONCERNING_ISSUE = {"YES"}

GOOD_SALES = {"GOOD", "GROWING", "STABLE", "STRONG"}
GOOD_EMI = {"ON_TIME", "ONTIME", "PAID", "REGULAR"}
GOOD_ISSUE = {"NO", "NONE"}


class LoanNotFoundError(Exception):
    pass


class MalformedSurveyResponseError(Exception):
    pass


def get_loan(loan_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM loans WHERE loan_id = ?", (loan_id,)).fetchone()
        return dict(row) if row else None


def send_survey(loan_id: str) -> dict:
    """Send the 3-question WhatsApp survey for a given loan and log the request."""
    loan = get_loan(loan_id)
    if loan is None:
        raise LoanNotFoundError(f"Loan '{loan_id}' does not exist")

    message = whatsapp.build_survey_message(loan["business_name"])
    result = whatsapp.send_whatsapp_message(loan["phone_number"], message)

    sent_at = utcnow_iso()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO survey_requests (loan_id, sent_at, channel, status) VALUES (?, ?, ?, ?)",
            (loan_id, sent_at, "whatsapp", result["status"]),
        )

    return {
        "loan_id": loan_id,
        "status": result["status"],
        "demo_mode": result["demo_mode"],
        "message_preview": message,
        "sent_at": sent_at,
    }


def _tokenize(message: str) -> list:
    """Split a free-text reply into up to 3 normalized tokens."""
    # Accept comma, semicolon, slash, or newline separated; collapse whitespace.
    raw_parts = re.split(r"[,\n;/]+", message.strip())
    tokens = [p.strip().upper().replace(" ", "_") for p in raw_parts if p.strip()]
    return tokens


def parse_survey_response(message: str) -> dict:
    """
    Parse a raw WhatsApp reply like 'GOOD, ON_TIME, NO' into normalized
    sales_status / emi_status / issue_status fields.

    Raises MalformedSurveyResponseError if fewer than 3 usable tokens are found.
    """
    tokens = _tokenize(message)
    if len(tokens) < 3:
        raise MalformedSurveyResponseError(
            f"Could not parse survey response '{message}'. Expected 3 answers "
            "such as 'GOOD, ON_TIME, NO' (sales, EMI, issue)."
        )

    sales_status, emi_status, issue_status = tokens[0], tokens[1], tokens[2]
    return {
        "sales_status": sales_status,
        "emi_status": emi_status,
        "issue_status": issue_status,
    }


def _is_concerning(field: str, value: str) -> bool:
    value = value.strip().upper()
    if field == "sales":
        if value in CONCERNING_SALES:
            return True
        if value in GOOD_SALES:
            return False
        # Unknown token: treat conservatively as NOT concerning to avoid false alerts,
        # but it's still recorded as-is for auditability.
        return False
    if field == "emi":
        if value in CONCERNING_EMI:
            return True
        if value in GOOD_EMI:
            return False
        return False
    if field == "issue":
        if value in CONCERNING_ISSUE:
            return True
        if value in GOOD_ISSUE:
            return False
        return False
    return False


def record_response(loan_id: str, raw_message: str) -> dict:
    """
    Parse + store a survey response, and create a mentor alert if the
    concerning-answer threshold is met (default: 2 or more).
    """
    loan = get_loan(loan_id)
    if loan is None:
        raise LoanNotFoundError(f"Loan '{loan_id}' does not exist")

    parsed = parse_survey_response(raw_message)

    concerning_flags = [
        _is_concerning("sales", parsed["sales_status"]),
        _is_concerning("emi", parsed["emi_status"]),
        _is_concerning("issue", parsed["issue_status"]),
    ]
    concerning_count = sum(concerning_flags)
    created_at = utcnow_iso()

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO survey_responses
               (loan_id, sales_status, emi_status, issue_status, concerning_count, raw_message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                loan_id,
                parsed["sales_status"],
                parsed["emi_status"],
                parsed["issue_status"],
                concerning_count,
                raw_message,
                created_at,
            ),
        )

    alert_created = False
    if concerning_count >= settings.CONCERNING_ANSWER_ALERT_THRESHOLD:
        reasons = []
        if concerning_flags[0]:
            reasons.append(f"Sales reported as '{parsed['sales_status']}'")
        if concerning_flags[1]:
            reasons.append(f"EMI status reported as '{parsed['emi_status']}'")
        if concerning_flags[2]:
            reasons.append(f"Business issue reported: '{parsed['issue_status']}'")
        reason = "; ".join(reasons) if reasons else "Multiple concerning survey answers"

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO mentor_alerts (loan_id, reason, created_at, resolved) VALUES (?, ?, ?, 0)",
                (loan_id, reason, created_at),
            )
        alert_created = True

    return {
        "loan_id": loan_id,
        "sales_status": parsed["sales_status"],
        "emi_status": parsed["emi_status"],
        "issue_status": parsed["issue_status"],
        "concerning_count": concerning_count,
        "alert_created": alert_created,
        "created_at": created_at,
    }


def list_all_loans() -> list:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM loans ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def list_alerts(resolved: Optional[bool] = None) -> list:
    with get_connection() as conn:
        if resolved is None:
            rows = conn.execute("SELECT * FROM mentor_alerts ORDER BY created_at DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM mentor_alerts WHERE resolved = ? ORDER BY created_at DESC",
                (1 if resolved else 0,),
            ).fetchall()
        return [dict(r) for r in rows]
