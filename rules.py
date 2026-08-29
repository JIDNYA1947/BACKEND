"""
Deterministic government scheme matching / eligibility explanation engine.

IMPORTANT: This is the SINGLE source of truth for eligibility decisions.
Feature 10 (matching) and Feature 12 (explanation) both call the exact same
functions here so there is only ONE rule engine in the codebase. No AI/LLM
call is made or required to decide eligibility - this module is 100%
deterministic and reads its criteria from app/data/schemes.json so scheme
rules can be edited without touching any Python code.
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings

MANDATORY_DISCLAIMER = settings.MANDATORY_DISCLAIMER


class SchemeDataError(Exception):
    """Raised when app/data/schemes.json is missing or malformed."""


def load_schemes_raw() -> Dict[str, Any]:
    """Load the raw schemes.json content. Not cached - always reflects the file on disk."""
    path: Path = settings.SCHEMES_FILE
    if not path.exists():
        raise SchemeDataError(f"Scheme data file not found at {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise SchemeDataError(f"Scheme data file is not valid JSON: {e}") from e

    if "schemes" not in data or not isinstance(data["schemes"], list):
        raise SchemeDataError("schemes.json must contain a top-level 'schemes' list")
    return data


def load_schemes() -> List[Dict[str, Any]]:
    return load_schemes_raw()["schemes"]


def get_scheme_by_id(scheme_id: str) -> Dict[str, Any]:
    for scheme in load_schemes():
        if scheme["scheme_id"].lower() == scheme_id.lower():
            return scheme
    raise SchemeDataError(f"Unknown scheme_id: {scheme_id}")


def _norm(value: str) -> str:
    return value.strip().lower()


def _list_condition(value: str, allowed: List[str]) -> bool:
    """An empty 'allowed' list means the criterion is a wildcard (any value matches)."""
    if not allowed:
        return True
    normalized_allowed = {_norm(a) for a in allowed}
    return _norm(value) in normalized_allowed


def _cost_condition(cost: float, cost_min: float, cost_max: float) -> bool:
    return cost_min <= cost <= cost_max


def evaluate_scheme(profile: Dict[str, Any], scheme: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate a single scheme against a business profile.

    Returns a dict with: scheme_id, scheme_name, passed, score, conditions
    (each condition includes condition/passed/actual/expected), disclaimer.

    This is the canonical, deterministic evaluation used by both the
    matching endpoint and the explanation endpoint.
    """
    criteria = scheme.get("criteria", {})

    business_types = criteria.get("business_types", [])
    cost_min = criteria.get("project_cost_min", 0)
    cost_max = criteria.get("project_cost_max", float("inf"))
    locations = criteria.get("locations", [])
    categories = criteria.get("categories", [])

    business_type_passed = _list_condition(profile["business_type"], business_types)
    cost_passed = _cost_condition(profile["project_cost"], cost_min, cost_max)
    location_passed = _list_condition(profile["location"], locations)
    category_passed = _list_condition(profile["category"], categories)

    def expected_str(allowed: List[str]) -> str:
        return "Any" if not allowed else ", ".join(allowed)

    conditions = [
        {
            "condition": "Business type matches",
            "passed": business_type_passed,
            "actual": profile["business_type"],
            "expected": expected_str(business_types),
        },
        {
            "condition": "Project cost is within configured range",
            "passed": cost_passed,
            "actual": f"₹{profile['project_cost']:,.0f}",
            "expected": f"₹{cost_min:,.0f} - ₹{cost_max:,.0f}" if cost_max != float("inf")
            else f"₹{cost_min:,.0f} and above",
        },
        {
            "condition": "Location condition matches",
            "passed": location_passed,
            "actual": profile["location"],
            "expected": expected_str(locations),
        },
        {
            "condition": "Category condition matches",
            "passed": category_passed,
            "actual": profile["category"],
            "expected": expected_str(categories),
        },
        {
            "condition": "Final eligibility subject to government/lender verification",
            "passed": True,
            "actual": "N/A",
            "expected": "Government/lender verification is always required",
        },
    ]

    core_conditions = conditions[:4]  # excludes the informational verification line
    passed_count = sum(1 for c in core_conditions if c["passed"])
    score = round((passed_count / len(core_conditions)) * 100, 2)
    overall_passed = all(c["passed"] for c in core_conditions)

    return {
        "scheme_id": scheme["scheme_id"],
        "scheme_name": scheme["scheme_name"],
        "passed": overall_passed,
        "score": score,
        "conditions": conditions,
        "disclaimer": scheme.get("disclaimer", MANDATORY_DISCLAIMER),
    }


def match_schemes(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Evaluate every configured scheme against the given profile."""
    return [evaluate_scheme(profile, scheme) for scheme in load_schemes()]


def explain_schemes(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Same deterministic engine as match_schemes - kept as a distinct entry
    point for Feature 12 readability, but it does NOT duplicate logic.
    """
    return match_schemes(profile)
