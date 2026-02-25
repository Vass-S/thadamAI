"""
LLM Verifier — Claude-powered checker for regex-extracted lab results.

Architecture:
  1. Regex pipeline runs first (fast, free, deterministic)
  2. This module sends raw text + regex results to Claude
  3. Claude checks each value against the source text
  4. Corrections + missed tests are returned as structured diffs
  5. Results are saved with llm_verified flag; diffs stored separately

The LLM is a CRITIC, not the primary extractor:
  - It can only correct values that exist in the raw text
  - It cannot invent values not present in the document
  - Every correction is stored so the user can accept/reject in the UI
"""

import json
import re
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd

# ─────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────

BASE_DIR    = Path(__file__).parent
DATA_DIR    = BASE_DIR / "data"
REVIEW_DIR  = DATA_DIR / "pending_review"
REVIEW_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────
# PROMPT
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are a medical lab report verification assistant.
You will receive:
  1. Raw text extracted from a lab report PDF
  2. A list of values a regex pipeline extracted from that text

Your job is to carefully check each extracted value against the raw text and:
  - CONFIRM values that are correct
  - CORRECT values that are wrong (wrong number, wrong unit, or value from reference range instead of result)
  - FLAG tests that appear in the raw text but were missed by the regex pipeline
  - IGNORE reference ranges, methodology notes, and interpretation text — only extract RESULT values

Rules you must follow:
  - You may ONLY report values that are explicitly present in the raw text
  - Do NOT invent, infer, or calculate values
  - For qualitative tests (Dengue NS1, cultures), use 0 for Negative and 1 for Positive, note the original text in a comment
  - If a value is ambiguous or you are not confident, set "confidence": "low"
  - Return ONLY valid JSON, no markdown, no explanation outside the JSON

Return this exact JSON structure:
{
  "patient_name": "NAME AS IN REPORT",
  "report_date": "YYYY-MM-DD",
  "verifications": [
    {
      "test": "canonical test name",
      "regex_value": 13.0,
      "regex_unit": "g/dL",
      "status": "confirmed" | "corrected" | "low_confidence",
      "correct_value": 13.0,
      "correct_unit": "g/dL",
      "confidence": "high" | "low",
      "note": "optional explanation if corrected or flagged"
    }
  ],
  "missed_tests": [
    {
      "test": "test name as written in report",
      "value": 4.5,
      "unit": "%",
      "confidence": "high" | "low",
      "note": "optional"
    }
  ]
}"""


def _build_user_message(raw_text: str, extracted: list[dict]) -> str:
    """Build the user message with raw text and extracted values."""
    extracted_str = json.dumps(extracted, indent=2, ensure_ascii=False)
    # Trim raw text if very long — keep first 6000 chars which covers most reports
    trimmed = raw_text[:6000] + ("\n...[truncated]" if len(raw_text) > 6000 else "")
    return (
        f"RAW REPORT TEXT:\n"
        f"================\n"
        f"{trimmed}\n\n"
        f"REGEX-EXTRACTED VALUES:\n"
        f"=======================\n"
        f"{extracted_str}\n\n"
        f"Please verify each extracted value and flag any missed tests."
    )


# ─────────────────────────────────────────────
# MAIN VERIFIER
# ─────────────────────────────────────────────

def verify_with_llm(
    raw_text: str,
    df: pd.DataFrame,
    api_key: Optional[str] = None,
) -> dict:
    """
    Send extracted results to Claude for verification.

    Args:
        raw_text:  The raw text extracted from the PDF (pre-OCR or post-OCR)
        df:        DataFrame from process_pdf() with columns:
                   test_name, value, unit, patient_name, report_date, ...
        api_key:   Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.

    Returns:
        dict with keys:
          "verifications": list of dicts (one per test)
          "missed_tests":  list of dicts (tests the regex missed)
          "patient_name":  str (LLM-read name for cross-check)
          "report_date":   str (LLM-read date for cross-check)
          "raw_response":  str (full LLM JSON, for audit)
          "error":         str or None
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return {"error": "No ANTHROPIC_API_KEY found. Set it in Streamlit secrets.", "verifications": [], "missed_tests": []}

    try:
        import anthropic
    except ImportError:
        return {"error": "anthropic package not installed. Add it to requirements.txt.", "verifications": [], "missed_tests": []}

    # Build the extracted list for the prompt
    extracted = []
    for _, row in df.iterrows():
        extracted.append({
            "test":  row["test_name"],
            "value": float(row["value"]) if pd.notna(row["value"]) else None,
            "unit":  str(row["unit"]) if pd.notna(row["unit"]) else "",
        })

    client = anthropic.Anthropic(api_key=key)

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",   # Fast + cost-effective for verification tasks
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": _build_user_message(raw_text, extracted),
            }],
        )
        raw_json = response.content[0].text.strip()

        # Strip markdown fences if model wraps in ```json
        raw_json = re.sub(r'^```(?:json)?\s*', '', raw_json, flags=re.M)
        raw_json = re.sub(r'\s*```$', '', raw_json, flags=re.M)

        result = json.loads(raw_json)
        result["raw_response"] = raw_json
        result["error"] = None
        return result

    except json.JSONDecodeError as e:
        return {
            "error": f"LLM returned invalid JSON: {e}",
            "raw_response": raw_json if 'raw_json' in dir() else "",
            "verifications": [],
            "missed_tests": [],
        }
    except Exception as e:
        return {
            "error": f"LLM API error: {e}",
            "verifications": [],
            "missed_tests": [],
        }


# ─────────────────────────────────────────────
# DIFF BUILDER
# ─────────────────────────────────────────────

def build_diff(df: pd.DataFrame, llm_result: dict) -> pd.DataFrame:
    """
    Compare regex results with LLM verification and return a diff DataFrame.

    Returns a DataFrame with columns:
      test_name, regex_value, regex_unit,
      llm_value, llm_unit, status,
      confidence, note, needs_review
    """
    if llm_result.get("error") or not llm_result.get("verifications"):
        return pd.DataFrame()

    rows = []
    verif_map = {v["test"]: v for v in llm_result.get("verifications", [])}

    for _, row in df.iterrows():
        test = row["test_name"]
        v = verif_map.get(test)

        if v is None:
            # LLM didn't mention this test — treat as confirmed
            rows.append({
                "test_name":   test,
                "regex_value": row["value"],
                "regex_unit":  row["unit"],
                "llm_value":   row["value"],
                "llm_unit":    row["unit"],
                "status":      "confirmed",
                "confidence":  "high",
                "note":        "",
                "needs_review": False,
            })
            continue

        llm_val  = v.get("correct_value", row["value"])
        llm_unit = v.get("correct_unit",  row["unit"])
        status   = v.get("status", "confirmed")
        conf     = v.get("confidence", "high")

        # Determine if this needs human review
        value_changed = (llm_val is not None and
                        abs(float(llm_val) - float(row["value"])) > 0.001)
        needs_review  = (status == "corrected" and value_changed) or conf == "low"

        rows.append({
            "test_name":   test,
            "regex_value": row["value"],
            "regex_unit":  row["unit"],
            "llm_value":   llm_val,
            "llm_unit":    llm_unit,
            "status":      status,
            "confidence":  conf,
            "note":        v.get("note", ""),
            "needs_review": needs_review,
        })

    # Add missed tests from LLM
    for m in llm_result.get("missed_tests", []):
        rows.append({
            "test_name":   m.get("test", "Unknown"),
            "regex_value": None,
            "regex_unit":  "",
            "llm_value":   m.get("value"),
            "llm_unit":    m.get("unit", ""),
            "status":      "missed_by_regex",
            "confidence":  m.get("confidence", "high"),
            "note":        m.get("note", "Found in report but not extracted by regex"),
            "needs_review": True,
        })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────
# APPLY CORRECTIONS
# ─────────────────────────────────────────────

def apply_corrections(df: pd.DataFrame, diff: pd.DataFrame, accepted_tests: list[str]) -> pd.DataFrame:
    """
    Apply LLM corrections to the main DataFrame for accepted tests.

    Args:
        df:             Original regex-extracted DataFrame
        diff:           Diff DataFrame from build_diff()
        accepted_tests: List of test_names the user accepted corrections for

    Returns:
        Updated DataFrame with corrected values.
    """
    if diff.empty:
        return df

    df = df.copy()
    correction_map = {}

    for _, row in diff.iterrows():
        if row["test_name"] in accepted_tests:
            if row["status"] in ("corrected", "missed_by_regex") and row["llm_value"] is not None:
                correction_map[row["test_name"]] = {
                    "value": row["llm_value"],
                    "unit":  row["llm_unit"],
                }

    # Apply corrections to existing rows
    for idx, row in df.iterrows():
        if row["test_name"] in correction_map:
            c = correction_map[row["test_name"]]
            df.at[idx, "value"]          = float(c["value"])
            df.at[idx, "unit"]           = c["unit"]
            df.at[idx, "llm_verified"]   = True
            df.at[idx, "llm_corrected"]  = True

    # Add missed tests as new rows
    missed_accepted = diff[
        (diff["status"] == "missed_by_regex") &
        (diff["test_name"].isin(accepted_tests))
    ]
    if not missed_accepted.empty and not df.empty:
        template = df.iloc[0].to_dict()
        new_rows = []
        for _, m in missed_accepted.iterrows():
            new_row = template.copy()
            new_row["test_name"]      = m["test_name"]
            new_row["value"]          = float(m["llm_value"]) if m["llm_value"] is not None else None
            new_row["unit"]           = m["llm_unit"]
            new_row["status"]         = "—"
            new_row["llm_verified"]   = True
            new_row["llm_corrected"]  = True
            new_rows.append(new_row)
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)

    return df


# ─────────────────────────────────────────────
# PENDING REVIEW STORE
# ─────────────────────────────────────────────

def save_pending_review(patient_id: str, report_date: str,
                        diff: pd.DataFrame, raw_text: str) -> Path:
    """Save a diff for later user review. Returns the path."""
    safe_date = str(report_date)[:10].replace("-", "")
    path = REVIEW_DIR / f"{patient_id}_{safe_date}.json"
    payload = {
        "patient_id":  patient_id,
        "report_date": str(report_date)[:10],
        "created_at":  datetime.now().isoformat(),
        "diff":        diff.to_dict(orient="records"),
        "raw_text_snippet": raw_text[:500],
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def load_pending_reviews() -> list[dict]:
    """Return all pending review files as a list of dicts."""
    reviews = []
    for f in sorted(REVIEW_DIR.glob("*.json"), reverse=True):
        try:
            reviews.append(json.loads(f.read_text()))
        except Exception:
            continue
    return reviews


def delete_pending_review(patient_id: str, report_date: str):
    """Remove a pending review file after user decision."""
    safe_date = str(report_date)[:10].replace("-", "")
    path = REVIEW_DIR / f"{patient_id}_{safe_date}.json"
    if path.exists():
        path.unlink()