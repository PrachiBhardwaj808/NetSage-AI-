"""
utils/data_loader.py
====================
Data loading, saving, and statistics utilities for NetSage AI.
"""

from __future__ import annotations
import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"
CASES_FILE = DATA_DIR / "cases.csv"
REVIEWS_FILE = DATA_DIR / "reviews.csv"

REVIEW_COLUMNS = [
    "case_id", "ai_root_cause", "ai_confidence", "human_decision",
    "human_correction", "review_reason", "reviewer", "timestamp"
]


# ─── Loaders ──────────────────────────────────────────────────────────────────

def load_cases() -> pd.DataFrame:
    """Load all 32 troubleshooting cases from cases.csv."""
    if not CASES_FILE.exists():
        raise FileNotFoundError(f"Cases file not found: {CASES_FILE}")
    df = pd.read_csv(CASES_FILE, dtype=str).fillna("")
    return df


def load_case_by_id(case_id: str) -> dict | None:
    """Return a single case as a dict, or None if not found."""
    df = load_cases()
    matches = df[df["case_id"] == case_id]
    if matches.empty:
        return None
    return matches.iloc[0].to_dict()


def load_reviews() -> pd.DataFrame:
    """Load all human review records from reviews.csv."""
    if not REVIEWS_FILE.exists():
        # Return empty DataFrame with correct columns
        return pd.DataFrame(columns=REVIEW_COLUMNS)
    df = pd.read_csv(REVIEWS_FILE, dtype=str).fillna("")
    # Ensure all columns exist
    for col in REVIEW_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df


# ─── Writer ───────────────────────────────────────────────────────────────────

def save_review(
    case_id: str,
    ai_root_cause: str,
    ai_confidence: float,
    human_decision: str,
    human_correction: str,
    review_reason: str,
    reviewer: str,
) -> None:
    """
    Append a single review record to reviews.csv.

    Args:
        case_id          : e.g. 'CASE-001'
        ai_root_cause    : The AI's diagnosis root_cause string
        ai_confidence    : Float 0–1
        human_decision   : 'Accepted' | 'Edited' | 'Rejected'
        human_correction : Human's corrected root cause (empty if Accepted)
        review_reason    : Explanation for the decision
        reviewer         : Reviewer name
    """
    valid_decisions = {"Accepted", "Edited", "Rejected"}
    if human_decision not in valid_decisions:
        raise ValueError(f"human_decision must be one of {valid_decisions}")

    record = {
        "case_id": case_id,
        "ai_root_cause": ai_root_cause,
        "ai_confidence": round(float(ai_confidence), 3),
        "human_decision": human_decision,
        "human_correction": human_correction,
        "review_reason": review_reason,
        "reviewer": reviewer,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    file_exists = REVIEWS_FILE.exists()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with open(REVIEWS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS, quoting=csv.QUOTE_ALL)
        if not file_exists:
            writer.writeheader()
        writer.writerow(record)


# ─── Statistics ───────────────────────────────────────────────────────────────

def get_dashboard_stats() -> dict[str, Any]:
    """
    Compute all metrics needed for the dashboard.

    Returns a dict with:
        total_cases, total_reviewed, accepted, edited, rejected,
        agreement_rate, cases_by_category, cases_by_severity,
        decisions_by_category, corrected_cases (Edited + Rejected rows)
    """
    cases_df = load_cases()
    reviews_df = load_reviews()

    total_cases = len(cases_df)

    # Review counts
    total_reviewed = len(reviews_df)
    accepted = len(reviews_df[reviews_df["human_decision"] == "Accepted"])
    edited = len(reviews_df[reviews_df["human_decision"] == "Edited"])
    rejected = len(reviews_df[reviews_df["human_decision"] == "Rejected"])

    agreement_rate = (accepted / total_reviewed * 100) if total_reviewed > 0 else 0.0

    # Cases by category
    cases_by_category = (
        cases_df.groupby("category").size().reset_index(name="count").to_dict(orient="records")
    )

    # Cases by severity
    cases_by_severity = (
        cases_df.groupby("severity").size().reset_index(name="count").to_dict(orient="records")
    )

    # Corrected cases (Edited or Rejected) for Responsible AI page
    corrected_mask = reviews_df["human_decision"].isin(["Edited", "Rejected"])
    corrected_cases = reviews_df[corrected_mask].to_dict(orient="records")

    return {
        "total_cases": total_cases,
        "total_reviewed": total_reviewed,
        "accepted": accepted,
        "edited": edited,
        "rejected": rejected,
        "agreement_rate": round(agreement_rate, 1),
        "cases_by_category": cases_by_category,
        "cases_by_severity": cases_by_severity,
        "corrected_cases": corrected_cases,
    }


def get_case_options() -> list[str]:
    """Return list of 'CASE-001 — Title' strings for UI dropdowns."""
    df = load_cases()
    return [f"{row['case_id']} — {row['title']}" for _, row in df.iterrows()]
