"""
Tests for Feature 10 (matching) and Feature 12 (explanation).
Both features are exercised through the FastAPI TestClient to also verify
request validation and response shape end-to-end.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.main import app
from app.config import settings

client = TestClient(app)


def test_food_processing_rural_matches_pmfme_pmegp_mudra():
    payload = {
        "business_type": "Food Processing",
        "project_cost": 800000,
        "location": "Rural",
        "category": "Eligible Category",
    }
    resp = client.post("/api/schemes/match", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    matched = set(data["matched_scheme_ids"])
    assert {"PMFME", "PMEGP", "MUDRA"}.issubset(matched)

    # Every scheme result must include the mandatory verification condition.
    for result in data["results"]:
        condition_names = [c["condition"] for c in result["conditions"]]
        assert "Final eligibility subject to government/lender verification" in condition_names


def test_non_matching_business_returns_no_matches():
    # A large, unrelated project cost + category should fail every scheme's criteria.
    payload = {
        "business_type": "Astrology Consulting",
        "project_cost": 50000000,
        "location": "Urban",
        "category": "Ineligible Category",
    }
    resp = client.post("/api/schemes/match", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["matched_scheme_ids"] == []
    # All results should be present but all failed
    assert len(data["results"]) >= 3
    assert all(r["passed"] is False for r in data["results"])


def test_explanation_contains_condition_by_condition_results():
    payload = {
        "business_type": "Food Processing",
        "project_cost": 800000,
        "location": "Rural",
        "category": "Eligible Category",
    }
    resp = client.post("/api/schemes/explain", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["explanations"]) >= 3
    for explanation in data["explanations"]:
        assert len(explanation["conditions"]) >= 4
        for cond in explanation["conditions"]:
            assert "condition" in cond
            assert "passed" in cond
            # actual/expected should be present for informativeness
            assert "actual" in cond
            assert "expected" in cond


def test_every_explanation_includes_mandatory_verification_condition():
    payload = {
        "business_type": "Food Processing",
        "project_cost": 800000,
        "location": "Rural",
        "category": "Eligible Category",
    }
    resp = client.post("/api/schemes/explain", json=payload)
    data = resp.json()

    for explanation in data["explanations"]:
        condition_texts = [c["condition"] for c in explanation["conditions"]]
        assert "Final eligibility subject to government/lender verification" in condition_texts

    assert data["mandatory_disclaimer"] == settings.MANDATORY_DISCLAIMER


def test_match_endpoint_validates_input():
    # Missing required fields should return a 422 validation error, not crash.
    resp = client.post("/api/schemes/match", json={"business_type": "Food Processing"})
    assert resp.status_code == 422


def test_list_schemes_endpoint_returns_configured_schemes():
    resp = client.get("/api/schemes")
    assert resp.status_code == 200
    data = resp.json()
    ids = {s["scheme_id"] for s in data["schemes"]}
    assert {"PMFME", "PMEGP", "MUDRA"}.issubset(ids)
