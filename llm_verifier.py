"""
llm_verifier.py  —  v6

In v6 the LLM does the extraction, not auditing.
This file retains only the pending-review storage functions so that:
  - The LLM Review tab can still let users manually flag/note issues
  - Manual corrections made in Patient Profiles tab3 are saved
  - app.py import statements don't need restructuring

The old verify_with_llm / build_diff / apply_corrections / get_metadata_corrections
functions are removed — extraction accuracy is now handled in lab_extractor.py.
"""

import json
from pathlib import Path

_STORE = Path(__file__).parent / "data" / "patient_profiles"
_STORE.mkdir(parents=True, exist_ok=True)
_PENDING_FILE = _STORE / "pending_reviews.json"


def _load_raw() -> list:
    if not _PENDING_FILE.exists():
        return []
    try:
        with open(_PENDING_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_raw(data: list) -> None:
    with open(_PENDING_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def save_pending_review(patient_id: str, report_date: str,
                        note: str = "", raw_text: str = "",
                        meta: dict = None) -> None:
    """
    Save a manual review note for a report.
    In v6 this is used for user-initiated flags only (not LLM audit diffs).
    """
    records = _load_raw()
    # Remove any existing entry for same patient/date
    records = [r for r in records
               if not (r["patient_id"] == patient_id
                       and str(r["report_date"])[:10] == str(report_date)[:10])]
    records.append({
        "patient_id":   patient_id,
        "report_date":  str(report_date)[:10],
        "note":         note,
        "meta":         meta or {},
    })
    _save_raw(records)


def load_pending_reviews() -> list:
    return _load_raw()


def delete_pending_review(patient_id: str, report_date: str) -> None:
    records = _load_raw()
    records = [r for r in records
               if not (r["patient_id"] == patient_id
                       and str(r.get("report_date", ""))[:10] == str(report_date)[:10])]
    _save_raw(records)