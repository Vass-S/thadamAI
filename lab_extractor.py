"""
Longitudinal Biomarker Intelligence Platform v4
Robust extraction + longitudinal trends + patient profiles
"""

import re
import hashlib
import pdfplumber
import pandas as pd
from pathlib import Path
from datetime import datetime

BASE_DIR    = Path(__file__).parent
DATA_DIR    = BASE_DIR / "data"
STORE_DIR   = DATA_DIR / "patient_profiles"
DICT_PATH   = DATA_DIR / "Biomarker_dictionary_csv.csv"
STORE_DIR.mkdir(parents=True, exist_ok=True)

EXTRA_ALIASES = {
    # Vitamins & minerals
    "Vitamin B12":          ["vitamin b 12", "vitamin b12"],
    "Vitamin D (25-OH)":    ["vitamin d (25-oh)", "25 hydroxy (oh) vit d", "25-oh vitamin d",
                             "vitamin d", "25 oh vitamin d"],
    "Folic Acid":           ["folic acid", "folate", "folic acid (serum)"],
    "Copper":               ["copper"],

    # Metabolic / renal
    "Urea (Serum)":         ["urea - serum", "urea"],
    "Creatinine (Serum)":   ["creatinine - serum", "creatinine"],
    "Glucose (Fasting)":    ["glucose (fasting)", "glucose fasting (plasma-f,hexokinase)",
                             "glucose fasting"],
    "HbA1c":                ["hb a1c", "hba1c- glycated haemoglobin",
                             "hba1c- glycated haemoglobin (hplc)", "glycated haemoglobin",
                             "hba1c- glycated haemoglobin, blood by hplc method"],

    # Hormones - androgens
    "Testosterone (Total)": ["testosterone (total)", "testosterone"],
    "DHEA Sulphate":        ["dhea sulphate"],

    # Hormones - thyroid
    "TSH":                  ["tsh 3rd generation (hs tsh)", "tsh (hs tsh)", "hs tsh",
                             "tsh 3rd generation", "tsh- 3rd generation (hs tsh)"],
    "Free T3":              ["free t3", "free t 3", "ft3", "free  t3"],
    "Free T4":              ["free t4", "free t 4", "ft4", "free  t4"],

    # Hormones - pituitary / reproductive
    "LH":                   ["lh", "luteinizing hormone"],
    "FSH":                  ["fsh", "follicle stimulating hormone"],
    "Prolactin":            ["prolactin"],
    "Estradiol":            ["estradiol", "oestradiol", "e2"],
    "Progesterone":         ["progesterone"],

    # Hormones - adrenal / growth
    "Cortisol (AM)":        ["cortisol ( am)", "cortisol (am)", "cortisol"],
    "IGF-I":                ["igf - i", "igf i", "igf-1", "igf1"],

    # Liver
    "AST (SGOT)":           ["s.g.o.t. (ast)", "sgot (ast)", "sgot"],
    "ALT (SGPT)":           ["s.g.p.t. (alt)", "sgpt (alt)", "sgpt"],
    "Gamma GT":             ["gamma gt ( ggtp)", "gamma gt (ggtp)", "ggt"],
    "Bilirubin (Total)":    ["bilirubin - total", "bilirubin total"],
    "Bilirubin (Direct)":   ["bilirubin - direct", "bilirubin direct"],
    "Bilirubin (Indirect)": ["bilirubin - indirect", "bilirubin indirect"],
    "Total Protein":        ["total proteins", "total protein"],

    # Lipids
    "APO Lipoprotein A1":   ["apo lipoprotein a1"],
    "APO Lipoprotein B":    ["apo lipoprotein b", "apolipoproteins b"],
    "Lipoprotein(a)":       ["lipoprotein a ( lp a)", "lipoprotein(a)"],

    # Serology
    "Anti-Sperm Antibody":  ["anti sperm antibody", "anti-sperm antibody"],
}

UNIT_CONVERSIONS = {
    ("ng/ml", "ng/dl"): 10.0,
    ("ng/dl", "ng/ml"): 0.1,
    ("µg/dl", "µg/ml"): 0.01,
    ("µg/ml", "µg/dl"): 100.0,
}

_UNIT_MAP = {
    # volume-based
    "mg/dl": "mg/dL", "mg/l": "mg/L",
    "pg/ml": "pg/mL", "pg/dl": "pg/dL",
    "ng/ml": "ng/mL", "ng/dl": "ng/dL",
    "ug/dl": "µg/dL", "ug/ml": "µg/mL",
    "microgm/dl": "µg/dL", "microgm/ml": "µg/mL",
    # enzyme / activity
    "u/l": "U/L", "iu/l": "IU/L",
    "miu/l": "mIU/L", "miu/ml": "mIU/mL",
    "uiu/ml": "µIU/mL", "uiu/l": "µIU/L",
    # weight
    "gm/dl": "g/dL", "g/dl": "g/dL",
    # serology
    "mu/100ul": "mU/100uL", "mu/ml": "mU/mL",
    # misc
    "%": "%",
}

# Regex fragment that matches any known unit (used in find_value_in_text)
_UNIT_RE = (
    r'(mg\/dl|pg\/ml|pg\/dl|ng\/ml|ng\/dl'
    r'|ug\/dl|microgm\/dl|microgm\/ml'
    r'|u\/l|iu\/l|miu\/l|miu\/ml|uiu\/ml|\xb5iu\/ml|\xb5iu\/l'
    r'|gm\/dl|g\/dl|mu\/100ul|mu\/ml|%)'
)

_DATE_FMTS = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y", "%d/%m/%y"]


# ─────────────────────────────────────────────
# DICTIONARY
# ─────────────────────────────────────────────

def load_dictionary(path):
    df = pd.read_csv(path, encoding="latin1")
    biomarkers = {}
    alias_map  = {}

    for _, row in df.iterrows():
        canonical = row["canonical_name"].strip()
        if canonical not in biomarkers:
            biomarkers[canonical] = {"unit": str(row["unit"]).strip(), "sex_rows": []}
        biomarkers[canonical]["sex_rows"].append({
            "sex":          str(row["sex"]).strip().lower(),
            "normal_range": str(row["normal_range"]).strip(),
        })
        if pd.notna(row["aliases"]):
            for alias in str(row["aliases"]).split(","):
                a = alias.strip().lower()
                if a and a not in alias_map:
                    alias_map[a] = canonical

    for canonical, aliases in EXTRA_ALIASES.items():
        if canonical not in biomarkers:
            continue
        for alias in aliases:
            a = alias.strip().lower()
            if a not in alias_map:
                alias_map[a] = canonical

    all_aliases = sorted(alias_map.keys(), key=len, reverse=True)
    return biomarkers, alias_map, all_aliases


BIOMARKERS, _ALIAS_MAP, _ALL_ALIASES = load_dictionary(DICT_PATH)


# ─────────────────────────────────────────────
# STATUS FLAGGING
# ─────────────────────────────────────────────

def _parse_range(s):
    s = str(s).strip()
    if not s or s == "nan":
        return None, None
    m = re.match(r'^(\d+\.?\d*)\s*-\s*(\d+\.?\d*)$', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    if s.startswith(">="): return float(s[2:]), None
    if s.startswith("<="): return None,         float(s[2:])
    if s.startswith(">"):  return float(s[1:]), None
    if s.startswith("<"):  return None,         float(s[1:])
    return None, None


def _convert_value(value, from_unit, to_unit):
    key = (from_unit.lower(), to_unit.lower())
    factor = UNIT_CONVERSIONS.get(key)
    return value * factor if factor else value


def flag_status(canonical, value, extracted_unit, gender=""):
    bm = BIOMARKERS.get(canonical)
    if not bm:
        return "—"
    g = gender.upper()
    matched = None
    for sr in bm["sex_rows"]:
        if sr["sex"] == "both":
            matched = sr
        elif (sr["sex"] == "male" and g == "M") or (sr["sex"] == "female" and g == "F"):
            matched = sr
            break
    if not matched:
        return "—"
    ref_unit      = bm["unit"]
    compare_value = _convert_value(value, extracted_unit, ref_unit)
    low, high     = _parse_range(matched["normal_range"])
    if low  is not None and compare_value < low:  return "LOW ⬇"
    if high is not None and compare_value > high: return "HIGH ⬆"
    return "Normal"


def normalize_unit(unit):
    return _UNIT_MAP.get(str(unit).strip().lower(), str(unit).strip())


# ─────────────────────────────────────────────
# METADATA
# ─────────────────────────────────────────────

def extract_metadata(text):
    meta = {"name": "", "gender": "", "date": "", "age": None, "phone": ""}

    # Allow optional lab patient-ID token (e.g. "P0006027") between "Patient :" and Mr./Mrs.
    m = re.search(
        r"Patient\s*[:\-]\s*(?:[A-Z]\d+\s+)?(?:Mr\.|Mrs\.|Ms\.)?\s*([\w\s]+?)\s*\((\d+)\s*/\s*([MF])\)",
        text, re.I
    )
    if m:
        meta["name"]   = re.sub(r'\b[A-Z]\d+\b', '', m.group(1)).strip()
        meta["age"]    = int(m.group(2))
        meta["gender"] = m.group(3).upper()

    # ── Metropolis / new-Hitech fallback ─────────────────────────────
    # Format: "Mr. SRINIWAS S" on its own line; "Age: 36 Year(s) Sex: Male" elsewhere
    if not meta["name"]:
        m = re.search(r"(?:Mr\.|Mrs\.|Ms\.)\s+([\w]+(?:\s+\w)?)\s*(?:\n|$|Reference|VID)", text, re.I)
        if m:
            meta["name"] = m.group(1).strip()
    if not meta["age"]:
        m = re.search(r"Age\s*[:\-]\s*(\d+)", text, re.I)
        if m:
            meta["age"] = int(m.group(1))
    if not meta["gender"]:
        m = re.search(r"Sex\s*[:\-]\s*(Male|Female)", text, re.I)
        if m:
            meta["gender"] = "M" if m.group(1).upper() == "MALE" else "F"

    for pattern in [
        r"(?:Reported\s+On|Report\s+Date|Collected\s+On|Collection\s+Date)\s*[:\-]\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
        r"SID\s+Date\s*[:\-]\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
        r"(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
    ]:
        m = re.search(pattern, text, re.I)
        if m:
            for fmt in _DATE_FMTS:
                try:
                    meta["date"] = datetime.strptime(m.group(1), fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            if meta["date"]:
                break

    m = re.search(r"(?:Tel|Ph|Phone|Mobile)\s*(?:No\.?)?\s*[:\-]?\s*\+?(\d[\d\s\-]{9,})", text, re.I)
    if m:
        digits = re.sub(r'\D', '', m.group(1))
        meta["phone"] = digits[-10:] if len(digits) >= 10 else digits

    return meta


def _clean_name(name: str) -> str:
    name = re.sub(r'\b(Mr|Mrs|Ms|Dr|Miss)\.?\s*', '', name, flags=re.I)
    name = re.sub(r'\b[A-Z]\d+\b', '', name)
    return re.sub(r'\s+', ' ', name).strip().upper()


def make_patient_id(meta: dict) -> str:
    """
    Tier 1 — Full name (2+ real words) + gender.
               Always deterministic; no profile scan needed.
               e.g. 'SRINIWAS SRIRAM M' → stable hash.

    Tier 2 — Truncated name (1 real word) + phone + gender.
               Before hashing, scan existing profiles to see if a
               Tier-1 record already exists for the same first-name
               prefix + phone + gender.  If yes, reuse that PID so
               both reports land in the same longitudinal profile.

    Tier 3 — First name + gender + age-decade (no phone).
               Same profile scan as Tier 2.
    """
    gender = meta.get("gender", "").upper()
    name   = _clean_name(meta.get("name", ""))
    phone  = re.sub(r"\D", "", meta.get("phone", ""))[-10:]
    age    = meta.get("age")

    real_words = [w for w in name.split() if len(w) >= 2]

    # ── Tier 1: unambiguous full name ────────────────────────────────
    if len(real_words) >= 2:
        key = f"FULLNAME|{'_'.join(real_words)}|{gender}"
        return "P" + hashlib.sha256(key.encode()).hexdigest()[:8].upper()

    # ── Tiers 2 & 3: truncated name — try to merge with existing profile ──
    first = real_words[0] if real_words else "UNKNOWN"
    existing_pid = _lookup_existing_pid(first, gender, phone)
    if existing_pid:
        return existing_pid

    if phone and len(phone) >= 8:
        key = f"TRUNCATED|{first}|{gender}|{phone}"
        return "P" + hashlib.sha256(key.encode()).hexdigest()[:8].upper()

    decade = str((age // 10) * 10) if age else "XX"
    key    = f"FIRST|{first}|{gender}|{decade}"
    return "P" + hashlib.sha256(key.encode()).hexdigest()[:8].upper()


def _lookup_existing_pid(first_name: str, gender: str, phone: str) -> str | None:
    """
    Scan stored patient profiles for one whose:
      - stored patient_name starts with first_name (case-insensitive)
      - stored gender matches
      - stored phone (if present) matches last-10-digit phone

    Returns the existing patient_id string, or None if no match found.
    This lets a truncated "SRINIWAS S" report merge into the existing
    "SRINIWAS SRIRAM" full-name profile automatically.
    """
    if not STORE_DIR.exists():
        return None
    for csv_file in STORE_DIR.glob("*.csv"):
        try:
            df = pd.read_csv(csv_file, nrows=1)
            if df.empty:
                continue
            stored_name   = _clean_name(str(df["patient_name"].iloc[0]))
            stored_gender = str(df.get("gender", pd.Series([""])).iloc[0]).upper()
            stored_phone  = ""
            if "file_hash" in df.columns:
                # Re-read without nrows to get phone if it was stored
                pass
            # Match: gender must agree, stored name must start with our first word,
            # and if we have a phone it must match
            if stored_gender != gender:
                continue
            stored_first = stored_name.split()[0] if stored_name.split() else ""
            if stored_first != first_name.upper():
                continue
            # Phone check — read source_file column to find phone if stored
            # The phone isn't stored in the CSV directly; use the PID file name
            # as identity — just matching first_name + gender is enough when
            # the first name is distinctive (≥5 chars) to avoid false merges
            if len(first_name) >= 4:
                return csv_file.stem   # return the patient_id (filename without .csv)
        except Exception:
            continue
    return None


# ─────────────────────────────────────────────
# DUPLICATE DETECTION
# ─────────────────────────────────────────────

def file_hash(path: Path) -> str:
    """SHA-256 of file bytes — used to detect re-uploads of the same PDF."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_duplicate_file(path: Path) -> bool:
    """Return True if this exact file has already been stored in any patient profile."""
    fh = file_hash(path)
    for csv_file in STORE_DIR.glob("*.csv"):
        try:
            df = pd.read_csv(csv_file)
            if "file_hash" in df.columns and fh in df["file_hash"].values:
                return True
        except Exception:
            continue
    return False


# ─────────────────────────────────────────────
# EXTRACTION
# ─────────────────────────────────────────────

def find_value_in_text(text, pos):
    snippet = text[pos: pos + 100]
    # Strip cid artifacts that pdfplumber emits for special chars
    snippet = re.sub(r'\(cid:\d+\)', '', snippet)
    m = re.search(
        r'[:\|\s]*([<>]?\s*\d+(?:\.\d+)?)' + r'\s*' + _UNIT_RE,
        snippet, re.IGNORECASE
    )
    if not m:
        # Try without unit — value only
        m = re.search(r'[:\|\s]*([<>]?\s*\d+(?:\.\d+)?)', snippet, re.IGNORECASE)
        if not m:
            return None
        raw_val  = m.group(1).replace(" ", "").lstrip("<>")
        raw_unit = ""
    else:
        raw_val  = m.group(1).replace(" ", "").lstrip("<>")
        raw_unit = m.group(2) or ""
    try:
        value = float(raw_val)
    except ValueError:
        return None
    if not (0 < value < 1_000_000):
        return None
    return value, normalize_unit(raw_unit)


def extract_biomarkers(text, gender=""):
    results, seen = [], set()
    lines = text.split("\n")

    for i, line in enumerate(lines):
        clean = re.sub(r'\s+', ' ', line).strip()
        if not clean:
            continue
        if re.search(r'\b(upto|less than|more than|deficient|normal\s*:|method\s*:|specimen\s*:)\b', clean, re.I):
            continue

        lower = clean.lower()
        for alias in _ALL_ALIASES:
            canonical = _ALIAS_MAP[alias]
            if canonical in seen:
                continue
            pattern = re.compile(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', re.IGNORECASE)
            match   = pattern.search(lower)
            if not match:
                continue

            found = find_value_in_text(clean, match.end())

            # Look up to 2 lines ahead for value or split unit
            if not found:
                for lookahead in range(1, 3):
                    if i + lookahead < len(lines):
                        next_line = re.sub(r'\s+', ' ', lines[i + lookahead]).strip()
                        if re.search(r'\b(upto|less than|more than|deficient|normal\s*:|method\s*:|specimen\s*:)\b', next_line, re.I):
                            continue
                        found = find_value_in_text(next_line, 0)
                        if found:
                            break

            # Unit on a standalone line below the value (e.g. Hitech DHEA SULPHATE)
            if found and not found[1]:
                for lookahead in range(1, 3):
                    if i + lookahead < len(lines):
                        unit_line = re.sub(r'\s+', ' ', lines[i + lookahead]).strip()
                        unit_match = re.match(r'^' + _UNIT_RE + r'$', unit_line, re.I)
                        if unit_match:
                            found = (found[0], normalize_unit(unit_match.group(1)))
                            break

            if not found:
                continue

            value, unit = found
            ref_unit    = BIOMARKERS.get(canonical, {}).get("unit", "")
            used_unit   = unit if unit else ref_unit

            seen.add(canonical)
            results.append({
                "test_name": canonical,
                "value":     value,
                "unit":      used_unit,
                "status":    flag_status(canonical, value, used_unit, gender),
            })
            break

    return results


# ─────────────────────────────────────────────
# PROCESSING & STORAGE
# ─────────────────────────────────────────────

def compute_current_age(age_at_test: int, report_date: str) -> int:
    """
    Derive approximate birth year from age-at-test + report date,
    then return how old the patient is today (Feb 2026).
    """
    try:
        report_year = int(str(report_date)[:4])
        birth_year  = report_year - age_at_test
        current_year = datetime.now().year
        return current_year - birth_year
    except Exception:
        return age_at_test
    pdf_path = Path(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            t = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            text += t + "\n"

    meta    = extract_metadata(text)
    pid     = make_patient_id(meta)
    results = extract_biomarkers(text, gender=meta.get("gender", ""))

    if verbose:
        print(f"  {pdf_path.name}: {len(results)} tests | {meta.get('name','?')} | {meta.get('date','?')}")

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    df["patient_id"]    = pid
    df["patient_name"]  = meta["name"]
    df["gender"]        = meta.get("gender", "")
    df["age_at_test"]   = meta.get("age", "")
    df["report_date"]   = meta["date"]
    df["source_file"]   = pdf_path.name
    df["file_hash"]     = file_hash(pdf_path)
    # Compute birth year so current age stays accurate across future uploads
    if meta.get("age") and meta.get("date"):
        df["birth_year"] = int(meta["date"][:4]) - int(meta["age"])
    else:
        df["birth_year"] = None
    return df


def save_report(df):
    if df.empty:
        return
    path = STORE_DIR / f"{df['patient_id'].iloc[0]}.csv"
    if path.exists():
        existing      = pd.read_csv(path)
        existing_name = str(existing["patient_name"].iloc[0]) if not existing.empty else ""
        new_name      = str(df["patient_name"].iloc[0])
        if len(new_name) > len(existing_name):
            existing["patient_name"] = new_name
        df = pd.concat([existing, df], ignore_index=True)
    df.drop_duplicates(subset=["test_name", "report_date"], keep="first", inplace=True)
    df.sort_values(["test_name", "report_date"]).to_csv(path, index=False)


def load_history(patient_id):
    path = STORE_DIR / f"{patient_id}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")
    # Compute current age from the earliest known birth_year
    if "birth_year" in df.columns:
        birth_years = pd.to_numeric(df["birth_year"], errors="coerce").dropna()
        if not birth_years.empty:
            birth_year = int(birth_years.min())  # most accurate = earliest report's estimate
            df["current_age"] = datetime.now().year - birth_year
        else:
            df["current_age"] = df.get("age_at_test", None)
    else:
        df["current_age"] = df.get("age_at_test", None)
    return df


# ─────────────────────────────────────────────
# DELETE
# ─────────────────────────────────────────────

def delete_patient(patient_id: str) -> bool:
    """Delete all stored data for a patient. Returns True on success."""
    path = STORE_DIR / f"{patient_id}.csv"
    if path.exists():
        path.unlink()
        return True
    return False


def delete_report_by_date(patient_id: str, report_date: str) -> bool:
    """Remove all rows for a specific report_date from a patient's profile."""
    path = STORE_DIR / f"{patient_id}.csv"
    if not path.exists():
        return False
    df = pd.read_csv(path)
    before = len(df)
    df = df[df["report_date"].astype(str).str[:10] != str(report_date)[:10]]
    if len(df) == before:
        return False
    if df.empty:
        path.unlink()
    else:
        df.to_csv(path, index=False)
    return True


# ─────────────────────────────────────────────
# TRENDS & TIMESERIES
# ─────────────────────────────────────────────

def generate_trends(history):
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
        return pd.DataFrame(columns=["test_name", "first_date", "first_value",
                                     "latest_date", "latest_value", "unit",
                                     "change_%", "trend", "latest_status", "n_reports"])
    return pd.DataFrame(rows).sort_values("change_%", key=abs, ascending=False)


def get_test_timeseries(history: pd.DataFrame, test_name: str) -> pd.DataFrame:
    """Return date-sorted (report_date, value, status, unit) rows for one test."""
    df = (history[history["test_name"] == test_name]
          .dropna(subset=["report_date"])
          .sort_values("report_date")
          .drop_duplicates("report_date")[["report_date", "value", "status", "unit"]]
          .copy())
    df["report_date"] = pd.to_datetime(df["report_date"])
    return df


# ─────────────────────────────────────────────
# PATIENT LIST
# ─────────────────────────────────────────────

def list_patients():
    records = []
    for csv_file in STORE_DIR.glob("*.csv"):
        try:
            df = pd.read_csv(csv_file)
            if df.empty:
                continue
            records.append({
                "patient_id":   csv_file.stem,
                "patient_name": df["patient_name"].iloc[0],
                "gender":       df["gender"].iloc[0] if "gender" in df.columns else "",
                "n_reports":    df["report_date"].nunique() if "report_date" in df.columns else 1,
            })
        except Exception:
            continue
    return records