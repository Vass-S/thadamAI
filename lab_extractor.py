"""
Longitudinal Biomarker Intelligence Platform
lab_extractor.py  —  v6  (Phase 1: LLM-first extraction + SQLite)

Pipeline per PDF:
  1. pdfplumber → raw text  (OCR fallback if text < 80 words)
  2. Claude Haiku → structured JSON  {patient, tests[]}
  3. Regex validation  (numeric values, date parsing, unit normalisation)
  4. Dictionary enrichment:
       known test  → 4-zone classification, canonical unit, category
       unknown test → lab's own reference_range for Normal/Abnormal
  5. SQLite upsert  (patients + biomarker_records)

Removed vs v5:
  - All lab profile JSON files and regex extraction profiles
  - EXTRA_ALIASES, alias scanning, extract_biomarkers(), extract_from_table()
  - extract_metadata() and all its kauvery/hitech/generic patterns
  - Per-patient CSV files  →  single SQLite database
"""

import re
import json
import hashlib
import sqlite3
import pdfplumber
import pandas as pd
import anthropic
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager

# ── OCR fallback (unchanged logic from v5) ────────────────────────────────────
try:
    from pdf2image import convert_from_path as _pdf2img
    import pytesseract as _tess
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent
DATA_DIR  = BASE_DIR / "data"
DICT_PATH = DATA_DIR / "Biomarker_dictionary_csv.csv"
DB_PATH   = DATA_DIR / "biomarker.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Kept for backward compat — llm_verifier.py stores pending reviews here
STORE_DIR = DATA_DIR / "patient_profiles"
STORE_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# SQLITE  — two tables, WAL mode, foreign keys
# =============================================================================

_SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    patient_id   TEXT PRIMARY KEY,
    patient_name TEXT NOT NULL,
    gender       TEXT DEFAULT '',
    birth_year   INTEGER,
    phone        TEXT DEFAULT '',
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS biomarker_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      TEXT NOT NULL REFERENCES patients(patient_id),
    report_date     TEXT NOT NULL,
    test_name       TEXT NOT NULL,
    raw_test_name   TEXT,
    canonical_name  TEXT,
    value           REAL NOT NULL,
    unit            TEXT DEFAULT '',
    reference_range TEXT DEFAULT '',
    status          TEXT DEFAULT '',
    category        TEXT DEFAULT '',
    lab_name        TEXT DEFAULT '',
    source_file     TEXT DEFAULT '',
    file_hash       TEXT DEFAULT '',
    ocr_extracted   INTEGER DEFAULT 0,
    age_at_test     INTEGER,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(patient_id, report_date, test_name)
);

CREATE INDEX IF NOT EXISTS idx_br_patient ON biomarker_records(patient_id);
CREATE INDEX IF NOT EXISTS idx_br_date    ON biomarker_records(report_date);
CREATE INDEX IF NOT EXISTS idx_br_hash    ON biomarker_records(file_hash);
"""


@contextmanager
def _db():
    """Yield a committed SQLite connection; rollback on exception."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _init_db():
    with _db() as conn:
        conn.executescript(_SCHEMA)


_init_db()


# =============================================================================
# BIOMARKER DICTIONARY  —  clinical zones, canonical units, categories
# =============================================================================

_UNIT_MAP = {
    "mg/dl": "mg/dL", "mg/l": "mg/L",
    "pg/ml": "pg/mL", "pg/dl": "pg/dL",
    "ng/ml": "ng/mL", "ng/dl": "ng/dL",
    "ug/dl": "µg/dL", "ug/ml": "µg/mL",
    "microgm/dl": "µg/dL", "microgm/ml": "µg/mL",
    "u/l": "U/L", "iu/l": "IU/L",
    "miu/l": "mIU/L", "miu/ml": "mIU/mL",
    "uiu/ml": "µIU/mL", "uiu/l": "µIU/L",
    "gm/dl": "g/dL", "g/dl": "g/dL",
    "10^6/ul": "10^6/µL", "10^6/µl": "10^6/µL",
    "10^3/ul": "10^3/µL", "10^3/µl": "10^3/µL",
    "mmol/l": "mmol/L", "umol/l": "µmol/L", "nmol/l": "nmol/L",
    "fl": "fL", "pg": "pg", "%": "%",
}

UNIT_CONVERSIONS = {
    ("ng/ml", "ng/dl"): 10.0,
    ("ng/dl", "ng/ml"): 0.1,
    ("µg/dl", "µg/ml"): 0.01,
    ("µg/ml", "µg/dl"): 100.0,
}

_DATE_FMTS = [
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%m/%d/%Y", "%d/%m/%y", "%B %d, %Y", "%b %d, %Y",
    "%d %B %Y", "%d %b %Y",
]


def normalize_unit(unit: str) -> str:
    raw = str(unit).strip()
    low = raw.lower().replace(" ", "")
    return _UNIT_MAP.get(low, raw)


def _safe_float(v):
    try:
        f = float(v)
        return None if (f != f) else f   # NaN check
    except (TypeError, ValueError):
        return None


def _load_dictionary(path: Path) -> dict:
    """
    Returns {canonical_name: {unit, category, sex_rows[], zone range floats,
                               short_description, interpretation_summary}}
    """
    try:
        df = pd.read_csv(path, encoding="latin1")
    except FileNotFoundError:
        return {}

    biomarkers = {}
    for _, row in df.iterrows():
        canonical = str(row.get("canonical_name", "")).strip()
        if not canonical or canonical == "nan":
            continue
        if canonical not in biomarkers:
            biomarkers[canonical] = {
                "unit":                   str(row.get("unit", "")).strip(),
                "category":               str(row.get("category", "")).strip(),
                "short_description":      str(row.get("short_description", "")),
                "interpretation_summary": str(row.get("interpretation_summary", "")),
                "sex_rows":               [],
                "optimal_min":   _safe_float(row.get("optimal_min")),
                "optimal_max":   _safe_float(row.get("optimal_max")),
                "high_risk_min": _safe_float(row.get("high_risk_min")),
                "high_risk_max": _safe_float(row.get("high_risk_max")),
                "diseased_min":  _safe_float(row.get("diseased_min")),
                "diseased_max":  _safe_float(row.get("diseased_max")),
                "normal_min":    _safe_float(row.get("normal_min")),
                "normal_max":    _safe_float(row.get("normal_max")),
            }
        biomarkers[canonical]["sex_rows"].append({
            "sex":          str(row.get("sex", "both")).strip().lower(),
            "normal_range": str(row.get("normal_range", "")).strip(),
        })
    return biomarkers


# Loaded once at import — ~131 entries, negligible memory
BIOMARKERS: dict = _load_dictionary(DICT_PATH)

# Sorted canonical names embedded verbatim in the LLM prompt
_CANONICAL_LIST: str = "\n".join(f"  - {n}" for n in sorted(BIOMARKERS))


# -- Status / zone classification ---------------------------------------------

def _parse_range(s: str) -> tuple:
    """Parse '4.0-11.0', '<200', '>=3.5' into (low, high) floats."""
    s = str(s).strip()
    if not s or s in ("nan", "none", "None", ""):
        return None, None
    m = re.match(r"^(\d+\.?\d*)\s*[-\u2013]\s*(\d+\.?\d*)$", s)
    if m:
        return float(m.group(1)), float(m.group(2))
    if s.startswith(">="):  return float(s[2:]), None
    if s.startswith("<="):  return None, float(s[2:])
    if s.startswith(">"):   return float(s[1:]),  None
    if s.startswith("<"):   return None,  float(s[1:])
    return None, None


def _convert(value: float, from_unit: str, to_unit: str) -> float:
    key = (from_unit.lower().strip(), to_unit.lower().strip())
    factor = UNIT_CONVERSIONS.get(key)
    return value * factor if factor else value


def flag_status(test_name: str, value: float, unit: str,
                gender: str = "", reference_range: str = "") -> str:
    """
    For known tests: use curated normal ranges (sex-specific when available).
    For unknown tests: use the lab's own reference_range string.
    Returns: 'Normal' | 'HIGH ⬆' | 'LOW ⬇' | '—'
    """
    bm = BIOMARKERS.get(test_name)
    if bm:
        g = gender.upper()
        matched = None
        for sr in bm["sex_rows"]:
            if sr["sex"] == "both":
                matched = sr
            elif (sr["sex"] == "male" and g == "M") or (sr["sex"] == "female" and g == "F"):
                matched = sr
                break
        if not matched and bm["sex_rows"]:
            matched = bm["sex_rows"][0]
        if matched:
            val = _convert(value, unit, bm["unit"])
            lo, hi = _parse_range(matched["normal_range"])
            if lo is not None and val < lo: return "LOW ⬇"
            if hi is not None and val > hi: return "HIGH ⬆"
            return "Normal"

    # Fallback: lab's own reference range
    if reference_range and str(reference_range).strip() not in ("", "nan", "None", "—"):
        lo, hi = _parse_range(reference_range)
        if lo is not None and value < lo: return "LOW ⬇"
        if hi is not None and value > hi: return "HIGH ⬆"
        if lo is not None or hi is not None:
            return "Normal"
    return "—"


# =============================================================================
# LLM EXTRACTION  —  Claude Haiku, single call per PDF
# =============================================================================

_SYSTEM_PROMPT = f"""You are a medical data extraction specialist. Extract all structured data from lab report text.

Return ONLY a single JSON object — no markdown, no explanation:
{{
  "patient_name": "full name as printed, or null",
  "age": integer or null,
  "gender": "M" or "F" or null,
  "report_date": "date exactly as printed e.g. 19/01/2026, or null",
  "lab_name": "laboratory name or null",
  "tests": [
    {{
      "name": "test name exactly as printed",
      "canonical_name": "best match from the preferred list below, or null if no match",
      "value": numeric value as a JSON number (never a string),
      "unit": "unit as printed, or empty string",
      "reference_range": "reference range as printed e.g. 4.0-11.0 or <200, or null"
    }}
  ]
}}

Preferred canonical test names (use these when the test matches):
{_CANONICAL_LIST}

Rules:
- Extract EVERY test that has a numeric value — do not skip any
- value must be a JSON number, never a string ("5.2" is wrong, 5.2 is correct)
- If value is printed as "<0.1" use 0.1; if ">500" use 500
- canonical_name: choose the closest preferred name, or null if nothing fits
- report_date: return exactly as printed, do NOT reformat to YYYY-MM-DD
- Do not invent values — only extract what is literally in the text"""


def _call_haiku(raw_text: str, api_key: str) -> dict:
    """
    Call Claude Haiku. Returns parsed JSON dict or {"error": "..."}.
    """
    client = anthropic.Anthropic(api_key=api_key)
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Extract all data from this lab report:\n\n{raw_text[:14000]}"
            }],
        )
        text = msg.content[0].text.strip()
        # Strip accidental markdown fences
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.M)
        text = re.sub(r"\s*```\s*$",       "", text, flags=re.M)
        return json.loads(text)
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse failed: {e}"}
    except anthropic.APIError as e:
        return {"error": f"API error: {e}"}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# VALIDATION  —  regex sanity-check on LLM output
# =============================================================================

_DATE_TIME_STRIP = re.compile(r"\s+\d{1,2}:\d{2}.*$")


def _parse_date(raw) -> str:
    """Normalise any date string to YYYY-MM-DD. Returns '' on failure."""
    if not raw or str(raw).strip().lower() in ("null", "none", "nan", ""):
        return ""
    s = _DATE_TIME_STRIP.sub("", str(raw).strip()).strip()
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _validate_gender(raw) -> str:
    s = str(raw or "").strip().upper()
    if s in ("M", "MALE"):   return "M"
    if s in ("F", "FEMALE"): return "F"
    return ""


def _validate_value(v):
    """Accept finite numbers in a physiologically plausible range."""
    f = _safe_float(v)
    if f is None:            return None
    if f < 0 or f > 1_000_000: return None
    return f


def _validate_canonical(name: str) -> str:
    """Accept only names actually in our dictionary."""
    if not name or str(name).lower() in ("null", "none", "nan", ""):
        return ""
    return name if name in BIOMARKERS else ""


def validate_llm_output(llm: dict) -> tuple:
    """
    Clean and validate LLM JSON output.
    Returns (cleaned_dict, list_of_warning_strings).
    """
    warnings = []
    out = {}

    raw_name = str(llm.get("patient_name") or "").strip()
    raw_name = re.sub(r"\b(Mr|Mrs|Ms|Dr|Miss)\.?\s*", "", raw_name, flags=re.I)
    out["patient_name"] = re.sub(r"\s+", " ", raw_name).strip().upper() or "UNKNOWN"

    out["age"] = None
    try:
        age = int(llm.get("age") or 0)
        if 0 < age < 130:
            out["age"] = age
    except (TypeError, ValueError):
        pass

    out["gender"]      = _validate_gender(llm.get("gender"))
    out["report_date"] = _parse_date(llm.get("report_date"))
    out["lab_name"]    = str(llm.get("lab_name") or "").strip()

    if not out["report_date"]:
        warnings.append("Report date could not be parsed — please verify")

    validated = []
    seen_names = set()

    for t in (llm.get("tests") or []):
        name = str(t.get("name") or "").strip()
        if not name:
            continue

        val = _validate_value(t.get("value"))
        if val is None:
            warnings.append(
                f"Skipped '{name}': value '{t.get('value')}' is not a valid number"
            )
            continue

        canonical  = _validate_canonical(str(t.get("canonical_name") or ""))
        store_name = canonical or name          # de-dup key and storage name
        if store_name in seen_names:
            continue
        seen_names.add(store_name)

        unit = normalize_unit(str(t.get("unit") or ""))
        ref  = str(t.get("reference_range") or "").strip()
        if ref.lower() in ("none", "null", "nan", ""):
            ref = ""

        validated.append({
            "name":            name,        # raw as printed in PDF
            "canonical_name":  canonical,   # matched to dict, or ""
            "store_name":      store_name,  # what is saved as test_name
            "value":           val,
            "unit":            unit,
            "reference_range": ref,
        })

    if not validated:
        warnings.append("No valid numeric test results found in extraction")

    out["tests"] = validated
    return out, warnings


# =============================================================================
# PATIENT ID  —  deterministic, collision-resistant
# =============================================================================

def _clean_name(name: str) -> str:
    name = re.sub(r"\b(Mr|Mrs|Ms|Dr|Miss)\.?\s*", "", name, flags=re.I)
    return re.sub(r"\s+", " ", name).strip().upper()


def make_patient_id(name: str, gender: str, birth_year, phone: str = "") -> str:
    """
    Deterministic SHA-256 patient ID.
    Priority: full name + gender > first name + phone > first name + birth decade
    """
    clean  = _clean_name(name)
    words  = [w for w in clean.split() if len(w) >= 2]
    g      = gender.upper() if gender else "U"
    digits = re.sub(r"\D", "", phone or "")[-10:]

    if len(words) >= 2:
        key = f"FULL|{'_'.join(words)}|{g}"
    elif words and len(digits) >= 8:
        key = f"PHONE|{words[0]}|{g}|{digits}"
    elif words and birth_year:
        decade = str((int(birth_year) % 100 // 10) * 10)
        key = f"FIRST|{words[0]}|{g}|{decade}"
    elif words:
        key = f"FIRST|{words[0]}|{g}|XX"
    else:
        key = f"UNK|{hashlib.md5(name.encode()).hexdigest()[:8]}"

    return "P" + hashlib.sha256(key.encode()).hexdigest()[:8].upper()


# =============================================================================
# DEDUPLICATION
# =============================================================================

def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_duplicate_file(path: Path) -> bool:
    fh = file_hash(path)
    with _db() as conn:
        row = conn.execute(
            "SELECT 1 FROM biomarker_records WHERE file_hash = ? LIMIT 1", (fh,)
        ).fetchone()
    return row is not None


# =============================================================================
# MAIN PIPELINE
# =============================================================================

def process_pdf(pdf_path, api_key: str, verbose: bool = False) -> tuple:
    """
    Full pipeline: PDF → validated DataFrame + raw text.
    Returns (df, raw_text). df is empty on any failure.

    DataFrame columns (same shape as v5, so app.py UI is unchanged):
      patient_id, patient_name, gender, age_at_test, birth_year, report_date,
      test_name, raw_test_name, canonical_name, value, unit, reference_range,
      status, category, lab_name, source_file, file_hash, ocr_extracted
    """
    pdf_path = Path(pdf_path)

    # Step 1: pdfplumber
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            pages_text.append(t)
    full_text = "\n".join(pages_text)

    # Step 2: OCR fallback (unchanged from v5)
    ocr_used = False
    if _OCR_AVAILABLE and len(full_text.split()) < 80:
        try:
            images    = _pdf2img(str(pdf_path), dpi=300)
            ocr_pages = [_tess.image_to_string(img, config="--psm 6") for img in images]
            ocr_text  = "\n".join(ocr_pages)
            if len(ocr_text.split()) > len(full_text.split()):
                full_text = ocr_text
                ocr_used  = True
        except Exception:
            pass

    if verbose:
        mode = "[OCR]" if ocr_used else "[pdfplumber]"
        print(f"  {pdf_path.name}: {len(full_text.split())} words {mode}")

    # Step 3: LLM extraction
    llm_raw = _call_haiku(full_text, api_key)
    if "error" in llm_raw:
        if verbose:
            print(f"  LLM error: {llm_raw['error']}")
        return pd.DataFrame(), full_text

    # Step 4: Validate
    data, warnings = validate_llm_output(llm_raw)
    if verbose:
        for w in warnings:
            print(f"    warning: {w}")

    if not data["tests"]:
        return pd.DataFrame(), full_text

    # Step 5: Enrich with dictionary + compute status
    fh          = file_hash(pdf_path)
    report_date = data["report_date"]
    gender      = data["gender"]
    age         = data["age"]
    birth_year  = (int(report_date[:4]) - age) if (age and report_date) else None
    pid         = make_patient_id(data["patient_name"], gender, birth_year)

    rows = []
    for t in data["tests"]:
        canonical = t["canonical_name"]
        bm        = BIOMARKERS.get(canonical) if canonical else None
        unit      = bm["unit"] if (bm and bm["unit"]) else t["unit"]
        category  = bm["category"] if bm else ""

        status = flag_status(
            canonical or t["store_name"],
            t["value"], t["unit"],
            gender=gender,
            reference_range=t["reference_range"],
        )

        rows.append({
            "patient_id":      pid,
            "patient_name":    data["patient_name"],
            "gender":          gender,
            "age_at_test":     age,
            "birth_year":      birth_year,
            "report_date":     report_date,
            "test_name":       t["store_name"],
            "raw_test_name":   t["name"],
            "canonical_name":  canonical,
            "value":           t["value"],
            "unit":            unit,
            "reference_range": t["reference_range"],
            "status":          status,
            "category":        category,
            "lab_name":        data["lab_name"],
            "source_file":     pdf_path.name,
            "file_hash":       fh,
            "ocr_extracted":   ocr_used,
        })

    if verbose:
        known = sum(1 for r in rows if r["canonical_name"])
        print(f"  -> {len(rows)} tests ({known} in dict, {len(rows)-known} uncategorised)"
              f" | {data['patient_name']} | {report_date}")

    return pd.DataFrame(rows), full_text


# =============================================================================
# STORAGE  —  SQLite upsert
# =============================================================================

def _to_py_int(v) -> int | None:
    """Convert numpy int / bytes / str to plain Python int, or None."""
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray)):
        # sqlite3.Row can return INTEGER columns as little-endian bytes on Py 3.13
        return int.from_bytes(v, "little", signed=True)
    try:
        i = int(v)
        return i if 0 < i < 3000 else None   # sanity-check for year values
    except (TypeError, ValueError):
        return None


def save_report(df: pd.DataFrame) -> None:
    """Upsert patient metadata and insert biomarker records. Ignores exact duplicates."""
    if df.empty:
        return
    r0  = df.iloc[0]
    pid = str(r0["patient_id"])

    # Always store birth_year as a plain Python int (not numpy.int64)
    birth_year = _to_py_int(r0.get("birth_year"))

    with _db() as conn:
        existing = conn.execute(
            "SELECT patient_name FROM patients WHERE patient_id = ?", (pid,)
        ).fetchone()
        new_name = str(r0.get("patient_name", "UNKNOWN"))

        if existing is None:
            conn.execute(
                "INSERT INTO patients(patient_id, patient_name, gender, birth_year, phone)"
                " VALUES (?, ?, ?, ?, ?)",
                (pid, new_name,
                 str(r0.get("gender", "")),
                 birth_year,
                 str(r0.get("phone", "")))
            )
        elif len(new_name) > len(existing["patient_name"]):
            # Longer extracted name is usually more complete
            conn.execute(
                "UPDATE patients SET patient_name = ? WHERE patient_id = ?",
                (new_name, pid)
            )

        for _, row in df.iterrows():
            conn.execute("""
                INSERT OR IGNORE INTO biomarker_records
                  (patient_id, report_date, test_name, raw_test_name, canonical_name,
                   value, unit, reference_range, status, category,
                   lab_name, source_file, file_hash, ocr_extracted, age_at_test)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pid,
                str(row.get("report_date", "")),
                str(row.get("test_name", "")),
                str(row.get("raw_test_name", "")),
                str(row.get("canonical_name") or ""),
                float(row["value"]),
                str(row.get("unit", "")),
                str(row.get("reference_range", "")),
                str(row.get("status", "")),
                str(row.get("category", "")),
                str(row.get("lab_name", "")),
                str(row.get("source_file", "")),
                str(row.get("file_hash", "")),
                int(bool(row.get("ocr_extracted", False))),
                row.get("age_at_test"),
            ))


# =============================================================================
# READ
# =============================================================================

def load_history(patient_id: str) -> pd.DataFrame:
    """Load all records for a patient as a DataFrame (report_date as datetime)."""
    with _db() as conn:
        patient = conn.execute(
            "SELECT * FROM patients WHERE patient_id = ?", (patient_id,)
        ).fetchone()
        rows = conn.execute(
            "SELECT * FROM biomarker_records WHERE patient_id = ?"
            " ORDER BY report_date, test_name",
            (patient_id,)
        ).fetchall()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([dict(r) for r in rows])
    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")

    if patient:
        df["patient_name"] = patient["patient_name"]
        df["gender"]       = patient["gender"]
        by = _to_py_int(patient["birth_year"])
        df["current_age"]  = (
            (datetime.now().year - by)
            if by else df.get("age_at_test", pd.Series(dtype="object"))
        )

    return df


def list_patients() -> list:
    """Single SQL query — O(1) regardless of patient count."""
    with _db() as conn:
        rows = conn.execute("""
            SELECT p.patient_id,
                   p.patient_name,
                   p.gender,
                   COUNT(DISTINCT b.report_date) AS n_reports,
                   MAX(b.report_date)             AS last_report
            FROM   patients p
            LEFT JOIN biomarker_records b USING(patient_id)
            GROUP  BY p.patient_id
            ORDER  BY p.patient_name
        """).fetchall()
    return [dict(r) for r in rows]


# =============================================================================
# PATIENT MANAGEMENT
# =============================================================================

def delete_patient(patient_id: str) -> bool:
    with _db() as conn:
        conn.execute("DELETE FROM biomarker_records WHERE patient_id = ?", (patient_id,))
        n = conn.execute(
            "DELETE FROM patients WHERE patient_id = ?", (patient_id,)
        ).rowcount
    return n > 0


def delete_report_by_date(patient_id: str, report_date: str) -> bool:
    date_str = str(report_date)[:10]
    with _db() as conn:
        n = conn.execute(
            "DELETE FROM biomarker_records WHERE patient_id = ? AND report_date = ?",
            (patient_id, date_str)
        ).rowcount
        remaining = conn.execute(
            "SELECT COUNT(*) FROM biomarker_records WHERE patient_id = ?",
            (patient_id,)
        ).fetchone()[0]
        if remaining == 0:
            conn.execute("DELETE FROM patients WHERE patient_id = ?", (patient_id,))
    return n > 0


def rename_patient(patient_id: str, new_name: str) -> bool:
    with _db() as conn:
        n = conn.execute(
            "UPDATE patients SET patient_name = ? WHERE patient_id = ?",
            (new_name.strip().upper(), patient_id)
        ).rowcount
    return n > 0


def merge_into_patient(source_id: str, target_id: str) -> bool:
    """Move all source records to target, delete source patient."""
    with _db() as conn:
        conn.execute(
            "UPDATE OR IGNORE biomarker_records SET patient_id = ? WHERE patient_id = ?",
            (target_id, source_id)
        )
        # Remaining records couldn't move due to UNIQUE conflicts — delete them
        conn.execute(
            "DELETE FROM biomarker_records WHERE patient_id = ?", (source_id,)
        )
        conn.execute("DELETE FROM patients WHERE patient_id = ?", (source_id,))
    return True


def patch_record(patient_id: str, report_date: str, test_name: str,
                 new_value: float = None, new_unit: str = None) -> bool:
    """Manually correct a value/unit and recompute status."""
    date_str = str(report_date)[:10]
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM biomarker_records"
            " WHERE patient_id = ? AND report_date = ? AND test_name = ?",
            (patient_id, date_str, test_name)
        ).fetchone()
        if not row:
            return False
        row = dict(row)
        p   = conn.execute(
            "SELECT gender FROM patients WHERE patient_id = ?", (patient_id,)
        ).fetchone()
        g    = p["gender"] if p else ""
        val  = new_value if new_value is not None else row["value"]
        unit = new_unit  if new_unit  is not None else row["unit"]
        status = flag_status(
            row.get("canonical_name") or test_name, val, unit,
            gender=g, reference_range=row.get("reference_range", "")
        )
        conn.execute(
            "UPDATE biomarker_records SET value = ?, unit = ?, status = ?"
            " WHERE patient_id = ? AND report_date = ? AND test_name = ?",
            (val, unit, status, patient_id, date_str, test_name)
        )
    return True


# =============================================================================
# ANALYTICS
# =============================================================================

def generate_trends(history: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for test, group in history.groupby("test_name"):
        group = (group.dropna(subset=["report_date"])
                      .sort_values("report_date")
                      .drop_duplicates("report_date"))
        if len(group) < 2:
            continue
        first, latest = group.iloc[0], group.iloc[-1]
        delta = latest["value"] - first["value"]
        pct   = round(delta / first["value"] * 100, 1) if first["value"] else 0
        rows.append({
            "test_name":     test,
            "first_date":    str(first["report_date"])[:10],
            "first_value":   first["value"],
            "latest_date":   str(latest["report_date"])[:10],
            "latest_value":  latest["value"],
            "unit":          latest["unit"] if pd.notna(latest["unit"]) else "",
            "change_%":      pct,
            "trend":         "↑" if delta > 0 else "↓",
            "latest_status": latest["status"],
            "n_reports":     len(group),
        })
    if not rows:
        return pd.DataFrame(columns=[
            "test_name", "first_date", "first_value", "latest_date",
            "latest_value", "unit", "change_%", "trend", "latest_status", "n_reports"
        ])
    return pd.DataFrame(rows).sort_values("change_%", key=abs, ascending=False)


def get_test_timeseries(history: pd.DataFrame, test_name: str) -> pd.DataFrame:
    df = (history[history["test_name"] == test_name]
          .dropna(subset=["report_date"])
          .sort_values("report_date")
          .drop_duplicates("report_date")[["report_date", "value", "status", "unit"]]
          .copy())
    df["report_date"] = pd.to_datetime(df["report_date"])
    return df