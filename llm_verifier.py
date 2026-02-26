"""
LLM Verifier — Claude-powered checker for regex-extracted lab results.

Architecture:
  1. Regex pipeline runs first (fast, free, deterministic)
  2. This module sends raw text + regex results to Claude
  3. Claude checks:
       a) each extracted value against the source text
       b) missing/wrong units
       c) missing/wrong report date
       d) values outside normal ranges (flagged, never invented)
       e) missed tests
  4. Results are stored as diffs; user accepts/rejects in the UI

The LLM is a CRITIC, never the primary extractor:
  - It can only report values that exist in the raw text
  - It cannot invent, infer or calculate values not present in the document
  - Every correction is stored so the user can accept/reject
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
You receive the raw text of a lab report and the values a regex pipeline already extracted.

YOUR FOUR TASKS
───────────────
1. VERIFY EXTRACTED VALUES
   - Compare every extracted value against the raw text.
   - If the value matches the report → status: "confirmed"
   - If the value is wrong (misread digit, reference range read instead of result, OCR error) →
     status: "corrected" with the correct value from the raw text.
   - CRITICAL: corrected values MUST appear verbatim in the raw text. Never invent or calculate.

2. CHECK UNITS
   - If the extracted unit is blank or wrong, correct it from the raw text.
   - Use the unit_note field to explain.

3. CHECK REPORT DATE
   - Read the report/collection/sample date from the raw text.
   - Return it in the "report_date" field as YYYY-MM-DD.
   - If you cannot find a date, return "report_date": null.
   - Common labels: Report Date, Collected Date, Sample Date, Test Date, Reported On, 
     Collection Date, Date of Collection, Analysis Date, SID Date.

4. FLAG OUT-OF-RANGE VALUES
   - For tests where you know the standard adult reference range, flag values that fall
     outside that range using range_flag.
   - range_flag values: "HIGH", "LOW", "CRITICAL_HIGH", "CRITICAL_LOW", "normal", "unknown"
   - NEVER change the extracted value because it is out of range.
   - If you are unsure of the reference range, use "unknown".

5. FLAG MISSED TESTS
   - Report any test result in the raw text that the regex pipeline missed.
   - Only include tests where you can read both a numeric value AND a unit from the raw text.
   - Never report a test unless both are present.

STRICT RULES
────────────
- You may ONLY report values that are explicitly present in the raw text.
- Do NOT invent, infer, interpolate or calculate any value.
- Do NOT change a value just because it looks abnormal — abnormal values are real data.
- For qualitative results (Negative/Positive), use 0 for Negative and 1 for Positive.
- If unsure about any correction, set confidence: "low".
- Return ONLY valid JSON with no markdown, no preamble, no explanation outside the JSON.

JSON STRUCTURE
──────────────
{
  "patient_name": "NAME AS IN REPORT or null",
  "report_date":  "YYYY-MM-DD or null",
  "date_source":  "label where you found the date, e.g. Collected Date",
  "metadata_issues": [
    "missing report date",
    "patient gender not found"
  ],
  "verifications": [
    {
      "test":         "exact test name from the extracted list",
      "regex_value":  123.4,
      "regex_unit":   "mg/dL",
      "status":       "confirmed | corrected | low_confidence",
      "correct_value": 123.4,
      "correct_unit":  "mg/dL",
      "unit_note":    "unit was blank, read from text as mg/dL",
      "range_flag":   "normal | HIGH | LOW | CRITICAL_HIGH | CRITICAL_LOW | unknown",
      "range_note":   "Reference range 70-99 mg/dL; value 145 is HIGH",
      "confidence":   "high | low",
      "note":         "optional explanation"
    }
  ],
  "missed_tests": [
    {
      "test":       "test name as written in the report",
      "value":      4.5,
      "unit":       "%",
      "range_flag": "normal | HIGH | LOW | CRITICAL_HIGH | CRITICAL_LOW | unknown",
      "confidence": "high | low",
      "note":       "found on line X"
    }
  ]
}"""


def _build_user_message(raw_text: str, extracted: list[dict],
                        regex_date: str, regex_name: str) -> str:
    extracted_str = json.dumps(extracted, indent=2, ensure_ascii=False)
    trimmed = raw_text[:8000] + ("\n...[truncated]" if len(raw_text) > 8000 else "")
    return (
        f"REGEX-EXTRACTED METADATA:\n"
        f"  Patient name : {regex_name or '(not extracted)'}\n"
        f"  Report date  : {regex_date or '(not extracted — this is a critical issue)'}\n\n"
        f"RAW REPORT TEXT:\n"
        f"================\n"
        f"{trimmed}\n\n"
        f"REGEX-EXTRACTED TEST VALUES:\n"
        f"============================\n"
        f"{extracted_str}\n\n"
        f"Please verify each extracted value, check units, find the report date "
        f"(especially if the regex date above is missing), flag out-of-range values, "
        f"and list any missed tests."
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
    Send extracted results to Claude for full verification.

    Returns dict with keys:
      verifications, missed_tests, patient_name, report_date,
      date_source, metadata_issues, raw_response, error
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return {"error": "No ANTHROPIC_API_KEY found. Set it in Streamlit secrets.",
                "verifications": [], "missed_tests": [], "metadata_issues": []}

    try:
        import anthropic
    except ImportError:
        return {"error": "anthropic package not installed. Add it to requirements.txt.",
                "verifications": [], "missed_tests": [], "metadata_issues": []}

    # Pull regex-extracted metadata for cross-check
    regex_date = str(df["report_date"].iloc[0]) if not df.empty and "report_date" in df.columns else ""
    regex_name = str(df["patient_name"].iloc[0]) if not df.empty and "patient_name" in df.columns else ""

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
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": _build_user_message(raw_text, extracted, regex_date, regex_name),
            }],
        )
        raw_json = response.content[0].text.strip()
        raw_json = re.sub(r'^```(?:json)?\s*', '', raw_json, flags=re.M)
        raw_json = re.sub(r'\s*```$', '', raw_json, flags=re.M)

        result = json.loads(raw_json)
        result["raw_response"] = raw_json
        result["error"] = None
        return result

    except json.JSONDecodeError as e:
        raw = raw_json if 'raw_json' in dir() else ""
        return {"error": f"LLM returned invalid JSON: {e}",
                "raw_response": raw, "verifications": [], "missed_tests": [], "metadata_issues": []}
    except Exception as e:
        return {"error": f"LLM API error: {e}",
                "verifications": [], "missed_tests": [], "metadata_issues": []}


# ─────────────────────────────────────────────
# DIFF BUILDER
# ─────────────────────────────────────────────

def build_diff(df: pd.DataFrame, llm_result: dict) -> pd.DataFrame:
    """
    Compare regex results with LLM verification.

    Returns DataFrame with columns:
      test_name, regex_value, regex_unit,
      llm_value, llm_unit, status,
      range_flag, range_note, unit_note,
      confidence, note, needs_review
    """
    if llm_result.get("error"):
        return pd.DataFrame()

    rows = []
    verif_map = {v["test"]: v for v in llm_result.get("verifications", [])}

    for _, row in df.iterrows():
        test = row["test_name"]
        v    = verif_map.get(test)

        if v is None:
            rows.append({
                "test_name":   test,
                "regex_value": row["value"],
                "regex_unit":  row["unit"],
                "llm_value":   row["value"],
                "llm_unit":    row["unit"],
                "status":      "confirmed",
                "range_flag":  "unknown",
                "range_note":  "",
                "unit_note":   "",
                "confidence":  "high",
                "note":        "",
                "needs_review": False,
            })
            continue

        llm_val  = v.get("correct_value", row["value"])
        llm_unit = v.get("correct_unit",  row["unit"])
        status   = v.get("status", "confirmed")
        conf     = v.get("confidence", "high")
        rflag    = v.get("range_flag", "unknown")
        rnote    = v.get("range_note", "")
        unote    = v.get("unit_note", "")

        value_changed = (llm_val is not None and
                         abs(float(llm_val) - float(row["value"])) > 0.001)
        unit_changed  = (str(llm_unit).strip() != str(row["unit"]).strip() and
                         str(llm_unit).strip() != "")

        needs_review = (
            (status == "corrected" and (value_changed or unit_changed)) or
            conf == "low" or
            rflag in ("HIGH", "LOW", "CRITICAL_HIGH", "CRITICAL_LOW")
        )

        rows.append({
            "test_name":   test,
            "regex_value": row["value"],
            "regex_unit":  row["unit"],
            "llm_value":   llm_val,
            "llm_unit":    llm_unit,
            "status":      status,
            "range_flag":  rflag,
            "range_note":  rnote,
            "unit_note":   unote,
            "confidence":  conf,
            "note":        v.get("note", ""),
            "needs_review": needs_review,
        })

    # Missed tests
    for m in llm_result.get("missed_tests", []):
        rows.append({
            "test_name":   m.get("test", "Unknown"),
            "regex_value": None,
            "regex_unit":  "",
            "llm_value":   m.get("value"),
            "llm_unit":    m.get("unit", ""),
            "status":      "missed_by_regex",
            "range_flag":  m.get("range_flag", "unknown"),
            "range_note":  "",
            "unit_note":   "",
            "confidence":  m.get("confidence", "high"),
            "note":        m.get("note", "Found in report but not extracted by regex"),
            "needs_review": True,
        })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────
# METADATA DIFF — date / name corrections
# ─────────────────────────────────────────────

def get_metadata_corrections(df: pd.DataFrame, llm_result: dict) -> dict:
    """
    Return metadata corrections (date, name) that the LLM found
    and the regex missed or got wrong.

    Returns dict:
      {
        "date_correction": "2024-11-28" | None,
        "name_correction": "JOHN SMITH" | None,
        "metadata_issues": [...],
        "date_source": "Collected Date",
      }
    """
    out = {
        "date_correction":  None,
        "name_correction":  None,
        "metadata_issues":  llm_result.get("metadata_issues", []),
        "date_source":      llm_result.get("date_source", ""),
    }

    regex_date = str(df["report_date"].iloc[0]) if not df.empty else ""
    llm_date   = llm_result.get("report_date")

    if llm_date and llm_date != "null":
        llm_date = str(llm_date).strip()
        # Accept if regex missed it entirely, or if it differs
        if not regex_date or regex_date in ("", "nan", "NaT", "None"):
            out["date_correction"] = llm_date
        elif llm_date != regex_date[:10]:
            out["date_correction"] = llm_date   # flag for review

    llm_name   = llm_result.get("patient_name")
    regex_name = str(df["patient_name"].iloc[0]) if not df.empty else ""
    if llm_name and llm_name != "null":
        llm_name = str(llm_name).strip().upper()
        if llm_name and llm_name != regex_name.upper():
            out["name_correction"] = llm_name

    return out


# ─────────────────────────────────────────────
# APPLY CORRECTIONS
# ─────────────────────────────────────────────

def apply_corrections(df: pd.DataFrame, diff: pd.DataFrame,
                      accepted_tests: list[str],
                      meta_corrections: Optional[dict] = None) -> pd.DataFrame:
    """
    Apply LLM corrections to the main DataFrame for accepted tests.
    Optionally applies metadata corrections (date, name).
    """
    if diff.empty:
        return df

    df = df.copy()

    # Apply metadata corrections first
    if meta_corrections:
        if meta_corrections.get("date_correction"):
            df["report_date"] = meta_corrections["date_correction"]
        if meta_corrections.get("name_correction"):
            df["patient_name"] = meta_corrections["name_correction"]

    correction_map = {}
    for _, row in diff.iterrows():
        if row["test_name"] in accepted_tests:
            if row["status"] in ("corrected", "missed_by_regex") and row["llm_value"] is not None:
                correction_map[row["test_name"]] = {
                    "value": row["llm_value"],
                    "unit":  row["llm_unit"],
                }

    # Apply value/unit corrections
    for idx, row in df.iterrows():
        if row["test_name"] in correction_map:
            c = correction_map[row["test_name"]]
            df.at[idx, "value"]         = float(c["value"])
            df.at[idx, "unit"]          = c["unit"]
            df.at[idx, "llm_verified"]  = True
            df.at[idx, "llm_corrected"] = True

    # Add missed tests as new rows
    missed_accepted = diff[
        (diff["status"] == "missed_by_regex") &
        (diff["test_name"].isin(accepted_tests))
    ]
    if not missed_accepted.empty and not df.empty:
        template = df.iloc[0].to_dict()
        new_rows = []
        for _, m in missed_accepted.iterrows():
            r = template.copy()
            r["test_name"]     = m["test_name"]
            r["value"]         = float(m["llm_value"]) if m["llm_value"] is not None else None
            r["unit"]          = m["llm_unit"]
            r["status"]        = "—"
            r["llm_verified"]  = True
            r["llm_corrected"] = True
            new_rows.append(r)
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)

    return df


# ─────────────────────────────────────────────
# PENDING REVIEW STORE
# ─────────────────────────────────────────────

def save_pending_review(patient_id: str, report_date: str,
                        diff: pd.DataFrame, raw_text: str,
                        meta_corrections: Optional[dict] = None) -> Path:
    """Save a diff for later user review."""
    safe_date = str(report_date)[:10].replace("-", "")
    path = REVIEW_DIR / f"{patient_id}_{safe_date}.json"
    payload = {
        "patient_id":       patient_id,
        "report_date":      str(report_date)[:10],
        "created_at":       datetime.now().isoformat(),
        "diff":             diff.to_dict(orient="records"),
        "meta_corrections": meta_corrections or {},
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