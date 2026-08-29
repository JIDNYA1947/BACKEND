"""
Tests for Feature 9: post-loan WhatsApp health checks and mentor alerts.

Uses a temporary SQLite database (isolated per test run) so tests never
touch the real app_data.db, and runs fully in DEMO_MODE (no Twilio
credentials required).
"""
import os
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Point the app at an isolated temp DB before importing the app config/database.
_tmp_db_fd, _tmp_db_path = tempfile.mkstemp(suffix=".db")
os.close(_tmp_db_fd)
os.environ["DATABASE_PATH"] = _tmp_db_path
os.environ["DEMO_MODE"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.database import init_db  # noqa: E402

client = TestClient(app)


def setup_module(module):
    init_db()


def _create_loan(loan_amount=250000):
    payload = {
        "user_id": f"user-{uuid.uuid4().hex[:6]}",
        "phone_number": "+919999999999",
        "business_name": "Test Snacks Pvt Ltd",
        "loan_amount": loan_amount,
    }
    resp = client.post("/api/loans", json=payload)
    assert resp.status_code == 201
    return resp.json()["loan_id"]


def test_send_health_check_for_unknown_loan_returns_404():
    resp = client.post("/api/health-checks/send/DOES-NOT-EXIST")
    assert resp.status_code == 404


def test_send_health_check_demo_mode_succeeds():
    loan_id = _create_loan()
    resp = client.post(f"/api/health-checks/send/{loan_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["demo_mode"] is True
    assert data["loan_id"] == loan_id


def test_two_concerning_answers_creates_mentor_alert():
    loan_id = _create_loan()
    # FALLING sales (concerning) + MISSED EMI (concerning) + NO issue (not concerning) = 2 concerning
    resp = client.post(
        "/api/health-checks/respond",
        json={"loan_id": loan_id, "message": "FALLING, MISSED, NO"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["concerning_count"] == 2
    assert data["alert_created"] is True

    alerts_resp = client.get("/api/alerts")
    assert alerts_resp.status_code == 200
    alerts = alerts_resp.json()["alerts"]
    assert any(a["loan_id"] == loan_id for a in alerts)


def test_one_concerning_answer_does_not_create_mentor_alert():
    loan_id = _create_loan()
    # Only EMI missed is concerning; sales good, no issue = 1 concerning answer
    resp = client.post(
        "/api/health-checks/respond",
        json={"loan_id": loan_id, "message": "GOOD, MISSED, NO"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["concerning_count"] == 1
    assert data["alert_created"] is False

    alerts_resp = client.get("/api/alerts")
    alerts = alerts_resp.json()["alerts"]
    assert not any(a["loan_id"] == loan_id for a in alerts)


def test_malformed_survey_response_returns_422():
    loan_id = _create_loan()
    resp = client.post(
        "/api/health-checks/respond",
        json={"loan_id": loan_id, "message": "just one word"},
    )
    assert resp.status_code == 422


def test_respond_for_unknown_loan_returns_404():
    resp = client.post(
        "/api/health-checks/respond",
        json={"loan_id": "NOT-A-REAL-LOAN", "message": "GOOD, ON_TIME, NO"},
    )
    assert resp.status_code == 404


def test_resolve_alert_endpoint():
    loan_id = _create_loan()
    client.post(
        "/api/health-checks/respond",
        json={"loan_id": loan_id, "message": "FALLING, MISSED, YES"},
    )
    alerts = client.get("/api/alerts").json()["alerts"]
    target = next(a for a in alerts if a["loan_id"] == loan_id)

    resp = client.patch(f"/api/alerts/{target['id']}/resolve")
    assert resp.status_code == 200
    assert resp.json()["resolved"] is True
