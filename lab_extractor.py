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

    # Ratios
    "LDL/HDL Ratio":        ["ldl/hdl ratio", "ldl hdl ratio"],
    "CHOL/HDL Ratio":       ["chol/hdl ratio", "chol hdl ratio"],

    # Glucose (post prandial)
    "Glucose (Post Prandial)": ["glucose-post prandial(2hrs)", "glucose post prandial(2hrs)",
                                "glucose post prandial", "glucose-post prandial"],

    # Apolipoproteins
    "APO Lipoprotein E":    ["apolipoproteins e", "apolipoprotein e", "apo lipoprotein e"],

    # ── Haematology (Full Blood Count) ──────────────────────────────
    "Haemoglobin":          ["haemoglobin", "hemoglobin", "hgb", "hb"],
    "Haematocrit":          ["haematocrit", "hematocrit", "hct",
                             "packed cell volume", "pcv"],
    "Total RBC Count":      ["total rbc count", "rbc count", "red blood cell count",
                             "red cell count", "rbc"],
    "MCV":                  ["mean corpuscular volume", "mcv",
                             "mean corpuscular volume (mcv)"],
    "MCH":                  ["mean corpuscular haemoglobin", "mch",
                             "(mch) mean corpuscular haemoglobin",
                             "mean corpuscular hemoglobin",
                             "mch (mean corpuscular haemoglobin)"],
    "MCHC":                 ["mean corpuscular haemoglobin concentration", "mchc",
                             "(mchc) mean corpuscular haemoglobin",
                             "mean corpuscular hemoglobin concentration",
                             "mchc (mean corpuscular haemoglobin concentration)"],
    "RDW-CV":               ["rdw - cv", "rdw-cv", "rdw cv", "rdw",
                             "red cell distribution width"],
    "Total WBC Count":      ["total wbc count", "wbc count", "white blood cell count",
                             "total leucocyte count", "tlc", "wbc",
                             "white cell count"],
    "Neutrophil":           ["neutrophil", "neutrophils", "neutrophil %",
                             "neutrophil count %"],
    "Lymphocyte":           ["lymphocyte", "lymphocytes", "lymphocyte %",
                             "lymphocyte count %"],
    "Monocyte":             ["monocyte", "monocytes", "monocyte %",
                             "monocyte count %"],
    "Eosinophil":           ["eosinophil", "eosinophils", "eosinophil %",
                             "eosinophil count %"],
    "Basophil":             ["basophil", "basophils", "basophil %",
                             "basophil count %"],
    "Absolute Neutrophil Count": ["absolute neutrophil count",
                                  "absolute neutrophil count (anc)", "anc"],
    "Absolute Lymphocyte Count": ["absolute lymphocyte count",
                                  "absolute lymphocyte count (alc)", "alc"],
    "Absolute Monocyte Count":   ["absolute monocyte count",
                                  "absolute monocyte count (amc)", "amc"],
    "Absolute Eosinophil Count": ["absolute eosinophil count",
                                  "absolute eosinophil count (aec)", "aec"],
    "Absolute Basophil Count":   ["absolute basophil count",
                                  "absolute basophil count (abc)", "abc"],
    "Platelet Count":       ["platelet count", "platelets", "plt",
                             "thrombocyte count"],

    # ── Inflammation / Infection ─────────────────────────────────────
    "C Reactive Protein":   ["c reactive protein", "crp", "c-reactive protein",
                             "hs crp", "high sensitivity crp", "hscrp",
                             "c reactive protein (crp)",
                             "reactive protein (crp)",   # OCR drops leading 'C'
                             "reactive protein"],
    "Dengue NS1 Antigen":   ["dengue ns1 antigen", "dengue ns1", "ns1 antigen",
                             "dengue ns1 ag"],
}

UNIT_CONVERSIONS = {
    ("ng/ml", "ng/dl"): 10.0,
    ("ng/dl", "ng/ml"): 0.1,
    ("µg/dl", "µg/ml"): 0.01,
    ("µg/ml", "µg/dl"): 100.0,
}

_UNIT_MAP = {
    # concentration
    "mg/dl": "mg/dL", "mg/l": "mg/L", "mg/ml": "mg/mL",   # mg/L used by CRP
    "pg/ml": "pg/mL", "pg/dl": "pg/dL",
    "ng/ml": "ng/mL", "ng/dl": "ng/dL",
    "ug/dl": "µg/dL", "ug/ml": "µg/mL",
    "microgm/dl": "µg/dL", "microgm/ml": "µg/mL",
    # enzyme / activity
    "u/l": "U/L", "iu/l": "IU/L",
    "miu/l": "mIU/L", "miu/ml": "mIU/mL",
    "uiu/ml": "µIU/mL", "uiu/l": "µIU/L",
    # weight / protein
    "gm/dl": "g/dL", "g/dl": "g/dL", "g/l": "g/L",
    # serology
    "mu/100ul": "mU/100uL", "mu/ml": "mU/mL",
    # haematology
    "fl": "fL",                            # MCV
    "pg": "pg",                            # MCH
    "cells/ul": "cells/µL",               # counts
    "cells/µl": "cells/µL",
    "/ul": "cells/µL", "/µl": "cells/µL",
    "million/ul": "million/µL",            # RBC
    "million/µl": "million/µL",
    "10^3/ul": "10³/µL",                  # Kauvery WBC / platelet / absolute counts
    "10^6/ul": "10⁶/µL",                  # Kauvery RBC
    "lakhs/cumm": "cells/µL",             # Indian lab alternate unit (1 lakh = 100,000)
    "cumm": "cells/µL",                   # cells per cubic mm = cells/µL
    # misc
    "%": "%",
}

# Regex fragment that matches any known unit (used in find_value_in_text)
_UNIT_RE = (
    r'(mg\/dl|mg\/l|mg\/ml'               # mg/dL (glucose etc), mg/L (CRP), mg/mL
    r'|pg\/ml|pg\/dl|ng\/ml|ng\/dl'
    r'|ug\/dl|microgm\/dl|microgm\/ml'
    r'|u\/l|iu\/l|miu\/l|miu\/ml|uiu\/ml|\xb5iu\/ml|\xb5iu\/l'
    r'|gm\/dl|g\/dl|g\/l|mu\/100ul|mu\/ml'
    r'|fl|cells\/ul|cells\/\xb5l|\/ul|\/\xb5l'
    r'|10\^3\/ul|10\^6\/ul'               # normalised Kauvery count units
    r'|million\/ul|million\/\xb5l|lakhs\/cumm|cumm|%)'
)

_DATE_FMTS = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y", "%d/%m/%y"]


# ─────────────────────────────────────────────
# DICTIONARY
# ─────────────────────────────────────────────

def load_dictionary(path):
    """
    Load biomarker definitions from CSV.

    CSV columns (all required):
      canonical_name  – display name used throughout the app  (e.g. "Haemoglobin")
      unit            – canonical unit                        (e.g. "g/dL")
      sex             – "male" | "female" | "both"
      normal_range    – "low-high" or "Negative" etc.        (e.g. "13-17")
      aliases         – comma-separated search strings        (e.g. "hb,hgb,hemoglobin")

    One canonical_name may have multiple rows (one per sex). 
    The aliases column replaces the hard-coded EXTRA_ALIASES dict — just add
    aliases directly in the CSV. EXTRA_ALIASES in code acts as a fallback only
    for tests not yet in the CSV.
    """
    df = pd.read_csv(path, encoding="latin1")
    biomarkers = {}
    alias_map  = {}

    # Guard: check required columns exist before iterating
    required_cols = {"canonical_name", "unit", "sex", "normal_range", "aliases"}
    missing_cols  = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(
            f"Biomarker CSV is missing columns: {missing_cols}. "
            f"Found: {list(df.columns)}. "
            f"Check the CSV header row is intact and not shifted."
        )

    import warnings
    for row_num, (_, row) in enumerate(df.iterrows(), start=2):  # start=2: row 1 = header
        # Skip blank rows silently — common artifact of Excel editing
        if pd.isna(row["canonical_name"]) or str(row["canonical_name"]).strip() == "":
            continue
        try:
            canonical = str(row["canonical_name"]).strip()
            if canonical not in biomarkers:
                biomarkers[canonical] = {"unit": str(row["unit"]).strip(), "sex_rows": []}
            biomarkers[canonical]["sex_rows"].append({
                "sex":          str(row["sex"]).strip().lower(),
                "normal_range": str(row["normal_range"]).strip(),
            })
            # CSV aliases take priority — process them first
            if pd.notna(row["aliases"]) and str(row["aliases"]).strip():
                for alias in str(row["aliases"]).split(","):
                    a = alias.strip().lower()
                    if a and a not in alias_map:
                        alias_map[a] = canonical
        except Exception as e:
            # Log the bad row but keep going — don't crash the whole app
            warnings.warn(f"Skipping CSV row {row_num} ('{row.get('canonical_name', '?')}\'): {e}")

    # EXTRA_ALIASES in code = fallback for tests not yet in CSV
    for canonical, aliases in EXTRA_ALIASES.items():
        if canonical not in biomarkers:
            # Test not in CSV at all — register a minimal entry so it can be flagged
            biomarkers[canonical] = {"unit": "", "sex_rows": [{"sex": "both", "normal_range": ""}]}
        for alias in aliases:
            a = alias.strip().lower()
            if a not in alias_map:          # CSV wins; code fallback fills gaps
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

def _clean_name_raw(raw: str) -> str:
    """
    Strip patient-ID tokens and OCR title artifacts from a raw name string.
    Handles: 'My, SRINIWAS SRIRAM' (OCR reads Mr. as My,),
             'P0011168 Mrs. BEVERLEY BARNES', 'Mr. VIJEY KUMAR KB', etc.
    """
    s = raw.strip()
    # 1. Strip patient ID tokens: letter followed by digits (P0011168, POO11168)
    s = re.sub(r'\b[A-Za-z][A-Za-z0-9]*\d+[A-Za-z0-9]*\b\s*', '', s).strip()
    # 2. Strip leading title artifacts: Mr. Mrs. Ms. Dr. My, (OCR misspellings of Mr.)
    s = re.sub(r'^(?:Mr|Mrs|Ms|Dr|My|M[a-z])[\.,\s]+', '', s, flags=re.I).strip()
    # 3. Strip any remaining leading punctuation
    s = re.sub(r'^[,.\s]+', '', s).strip()
    return s.upper()


def extract_metadata(text):
    meta = {"name": "", "gender": "", "date": "", "age": None, "phone": ""}

    # ── Format 1: Old Hitech ─────────────────────────────────────────
    # 'Patient : P0011168 Mr. SRINIWAS SRIRAM (34/M)' or
    # 'Patient : POO11168 My, SRINIWAS SRIRAM (34/M)'  ← OCR artifact
    m = re.search(
        r"Patient\s*[:\-]\s*(.+?)\s*\((\d+)\s*/\s*([MF])\)",
        text, re.I
    )
    if m:
        meta["name"]   = _clean_name_raw(m.group(1))
        meta["age"]    = int(m.group(2))
        meta["gender"] = m.group(3).upper()

    # ── Format 2: Kauvery Hospital ───────────────────────────────────
    # 'Patient Name : Mr. Vijey Kumar KB'
    # 'Age / Gender : 39/Years/Male'
    if not meta["name"]:
        m = re.search(
            r"Patient\s+Name\s*[:\-]\s*(?:Mr\.|Mrs\.|Ms\.|Dr\.)?\s*([\w\s]+?)\s*"
            r"(?:Order|Collected|Report\s+Date|\n|$)",
            text, re.I
        )
        if m:
            meta["name"] = m.group(1).strip().upper()
    if not meta["age"] or not meta["gender"]:
        m = re.search(r"Age\s*/\s*Gender\s*[:\-]\s*(\d+)\s*/\s*Years?\s*/\s*(Male|Female)", text, re.I)
        if m:
            if not meta["age"]:    meta["age"]    = int(m.group(1))
            if not meta["gender"]: meta["gender"] = "M" if "male" in m.group(2).lower() else "F"

    # ── Format 3: New Hitech / Metropolis ────────────────────────────
    # 'Mrs. BAVERLEY B  Reference: SELF  VID: ...'
    # 'Age: 36 Year(s)  Sex: Female'
    if not meta["name"]:
        m = re.search(r"(?:Mr\.|Mrs\.|Ms\.)\s+([\w]+(?:\s+[\w]+)*)\s*(?:Reference|VID|\n|$)", text, re.I)
        if m:
            meta["name"] = m.group(1).strip().upper()
    if not meta["age"]:
        m = re.search(r"Age\s*[:\-]?\s*(\d+)", text, re.I)
        if m: meta["age"] = int(m.group(1))
    if not meta["gender"]:
        m = re.search(r"Sex\s*[:\-]\s*(Male|Female)", text, re.I)
        if m: meta["gender"] = "M" if m.group(1).upper() == "MALE" else "F"

    # ── Date ─────────────────────────────────────────────────────────
    _MONTH_MAP = {
        "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
        "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
    }
    _DATE_FMTS_EXT = _DATE_FMTS + ["%d/%m/%y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y",
                                     "%B %d, %Y", "%d %B %Y", "%d.%b.%Y"]

    def _try_parse(s):
        """Try every known format; also handle '28 Nov 2024' style."""
        s = s.strip()
        for fmt in _DATE_FMTS_EXT:
            try:
                return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
        # Named month: 28-Nov-2024 / 28 Nov 2024 / Nov 28 2024 etc.
        nm = re.match(
            r"(\d{1,2})[-\s\.]([A-Za-z]{3,9})[-\s\.](\d{2,4})|"
            r"([A-Za-z]{3,9})[-\s\.](\d{1,2})[-\s\.](\d{2,4})",
            s)
        if nm:
            try:
                if nm.group(1):  # dd-Mon-yyyy
                    d, mon, y = nm.group(1), nm.group(2)[:3].lower(), nm.group(3)
                else:            # Mon-dd-yyyy
                    mon, d, y = nm.group(4)[:3].lower(), nm.group(5), nm.group(6)
                mo = _MONTH_MAP.get(mon)
                if mo:
                    yr = int(y) + (2000 if len(y)==2 else 0)
                    return datetime(yr, mo, int(d)).strftime("%Y-%m-%d")
            except Exception:
                pass
        return ""

    for pattern in [
        # Labelled date (most reliable — try first)
        r"(?:Report\s+Date|Reported\s+On|Collected\s+Date|Collected\s+On|"
        r"Collection\s+Date|Sample\s+(?:Collection\s+)?Date|Test\s+Date|"
        r"Analysis\s+Date|Date\s+of\s+(?:Collection|Report|Test)|"
        r"Received\s+Date|Processed\s+Date|Authorised\s+(?:Date|On)|"
        r"SID\s+Date)\s*[:\-]?\s*"
        r"(\d{1,2}[\s\/\-\.][\w]{2,9}[\s\/\-\.]\d{2,4}"
        r"|\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}"
        r"|\d{4}-\d{2}-\d{2})",
        # ISO format yyyy-mm-dd anywhere
        r"(\d{4}-\d{2}-\d{2})",
        # dd-Mon-yyyy or dd Mon yyyy anywhere
        r"(\d{1,2}[-\s][A-Za-z]{3,9}[-\s]\d{4})",
        # Fallback: bare dd/mm/yyyy or dd-mm-yyyy
        r"(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        # Two-digit year fallback dd/mm/yy
        r"(\d{2}[\/\-]\d{2}[\/\-]\d{2})\b",
    ]:
        m = re.search(pattern, text, re.I)
        if m:
            parsed = _try_parse(m.group(1))
            if parsed:
                meta["date"] = parsed
                break

    # ── Phone ─────────────────────────────────────────────────────────
    # 'TelNo' handles OCR merging of Tel+No without space
    m = re.search(r"(?:Tel\s*No|TelNo|Ph|Phone|Mobile)\s*(?:No\.?)?\s*[:\-]?\s*\+?\s*(\d{10})\b", text, re.I)
    if m:
        meta["phone"] = m.group(1)

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

    # Special case: Kauvery-style qualitative results e.g. 'Negative(0.00)'
    qm = re.search(r'(?:Negative|Positive)\s*\(\s*(\d+(?:\.\d+)?)\s*\)', snippet, re.I)
    if qm:
        try:
            return float(qm.group(1)), ""
        except ValueError:
            pass

    m = re.search(
        r'[:\|\s]*([<>]?\s*\d+(?:\.\d+)?)' + r'\s*' + _UNIT_RE,
        snippet, re.IGNORECASE
    )
    if not m:
        # Try without unit — value only
        m = re.search(r'[:\|\s.]*([<>]?\s*\d+(?:\.\d+)?)', snippet, re.IGNORECASE)
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
    # Allow 0.0 (e.g. Dengue NS1 Negative = 0.00), but reject negatives
    if value < 0 or value >= 1_000_000:
        return None
    return value, normalize_unit(raw_unit)


def _normalize_count_units(text: str) -> str:
    """
    Normalize Kauvery-style haematology count units that OCR misreads.
      10^6/µL → written as '10°6/uL', '106/uL'
      10^3/µL → OCR'd as '1043/uL', '1043/pL', '10°3/pL', '10^3/yL'
    All are normalised to '10^3/uL' which is in _UNIT_MAP.
    """
    # 10^6/µL variants (OCR reads ° for ^ and the digit gets merged)
    text = re.sub(r'10[°\^oO][6]/[uµypUP][Ll]', '10^6/uL', text)
    # 10^3/µL variants
    text = re.sub(r'10[°\^oO][3]/[uµypUP][Ll]', '10^3/uL', text)
    # '1043/uL', '1043/pL', '1043/yL' — OCR merges '10^3' as '1043'
    text = re.sub(r'\b1043/[uµypUP][Ll]\b', '10^3/uL', text)
    return text


def extract_biomarkers(text, gender=""):
    results, seen = [], set()
    # Normalize OCR count-unit artifacts before line-by-line processing
    text = _normalize_count_units(text)
    lines = text.split("\n")

    for i, line in enumerate(lines):
        clean = re.sub(r'\s+', ' ', line).strip()
        if not clean:
            continue
        # Skip reference range / methodology / interpretation lines
        if re.search(
            r'\b(upto|less than|more than|deficient|normal\s*:|method\s*:|specimen\s*:|'
            r'associated tests|interpretation|clinical utility|references?\s*:|'
            r'note\s*:|disclaimer|decreased levels|increased levels|pregnancy)\b',
            clean, re.I
        ):
            continue
        # Skip numbered annotation lines (e.g. "1. HbA1c is used for...")
        if re.match(r'^\d+[\.\)]\s+[A-Z]', clean):
            continue
        # Skip lines that are purely a lab test code reference e.g. "(H0018)"
        if re.search(r'\([A-Z]\d{4,}\)', clean):
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
                        if re.search(
                            r'\b(upto|less than|more than|deficient|normal\s*:|method\s*:|specimen\s*:|'
                            r'associated tests|interpretation|clinical utility|note\s*:|disclaimer)\b',
                            next_line, re.I
                        ):
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
    then return how old the patient is today.
    """
    try:
        report_year = int(str(report_date)[:4])
        birth_year  = report_year - age_at_test
        current_year = datetime.now().year
        return current_year - birth_year
    except Exception:
        return age_at_test


# ─────────────────────────────────────────────
# OCR FALLBACK
# ─────────────────────────────────────────────

# Minimum characters of meaningful text required to trust pdfplumber output.
# Image-only PDFs return near-empty strings; anything below this triggers OCR.
_OCR_THRESHOLD = 150


def _strip_ocr_line_noise(text: str) -> str:
    """
    Strip barcode/logo OCR artifacts (—, ==, =n, etc.) from line beginnings.
    These appear when Tesseract reads the barcode column on the left margin
    of Hitech-format reports.
    """
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        # Remove any leading run of non-alphanumeric, non-parenthesis chars
        cleaned.append(re.sub(r'^[^A-Za-z0-9(]+', '', line))
    return "\n".join(cleaned)


def _extract_text_ocr(pdf_path: Path) -> str:
    """
    Convert each PDF page to a 300-dpi image and run Tesseract OCR.
    Returns combined text. Raises ImportError if dependencies are missing.
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError as e:
        raise ImportError(
            "OCR requires pdf2image and pytesseract. "
            "Add 'pdf2image pytesseract' to requirements.txt "
            "and 'tesseract-ocr poppler-utils' to packages.txt."
        ) from e

    pages = convert_from_path(str(pdf_path), dpi=300)
    text = ""
    for page in pages:
        # --oem 3  : LSTM engine (best accuracy)
        # --psm 6  : Assume uniform block of text (handles multi-column forms well)
        page_text = pytesseract.image_to_string(
            page, config="--oem 3 --psm 6"
        )
        text += page_text + "\n"
    # Strip leading barcode/logo artifacts from each line
    return _strip_ocr_line_noise(text)


def _is_image_pdf(text: str) -> bool:
    """Return True if pdfplumber extracted too little text to be useful."""
    # Count only alphanumeric chars — ignore whitespace and noise
    useful = re.sub(r'\s+', '', text)
    return len(useful) < _OCR_THRESHOLD


def process_pdf(pdf_path, verbose=True):
    pdf_path = Path(pdf_path)

    # ── Pass 1: pdfplumber (fast, exact for machine-readable PDFs) ──
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            t = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            text += t + "\n"

    ocr_used = False

    # ── Pass 2: OCR fallback for image/scanned PDFs ──────────────────
    if _is_image_pdf(text):
        if verbose:
            print(f"  {pdf_path.name}: low text yield — switching to OCR…")
        try:
            text = _extract_text_ocr(pdf_path)
            ocr_used = True
        except ImportError as e:
            if verbose:
                print(f"  OCR unavailable: {e}")
            return pd.DataFrame(), ""

    meta    = extract_metadata(text)
    pid     = make_patient_id(meta)
    results = extract_biomarkers(text, gender=meta.get("gender", ""))

    if verbose:
        mode = " [OCR]" if ocr_used else ""
        print(f"  {pdf_path.name}{mode}: {len(results)} tests | "
              f"{meta.get('name','?')} | {meta.get('date','?')}")

    if not results:
        return pd.DataFrame(), text

    df = pd.DataFrame(results)
    df["patient_id"]    = pid
    df["patient_name"]  = meta["name"]
    df["gender"]        = meta.get("gender", "")
    df["age_at_test"]   = meta.get("age", "")
    df["report_date"]   = meta["date"]
    df["source_file"]   = pdf_path.name
    df["file_hash"]     = file_hash(pdf_path)
    df["ocr_extracted"] = ocr_used
    df["llm_verified"]  = False   # set to True after LLM review + acceptance
    df["llm_corrected"] = False   # set to True if value was changed by LLM
    if meta.get("age") and meta.get("date"):
        df["birth_year"] = int(meta["date"][:4]) - int(meta["age"])
    else:
        df["birth_year"] = None
    return df, text   # return raw_text so caller can pass it to LLM verifier



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
# RENAME / MERGE
# ─────────────────────────────────────────────

def rename_patient(patient_id: str, new_name: str) -> bool:
    """Update patient_name in all rows of an existing profile."""
    path = STORE_DIR / f"{patient_id}.csv"
    if not path.exists():
        return False
    df = pd.read_csv(path)
    df["patient_name"] = new_name.strip().upper()
    df.to_csv(path, index=False)
    return True


def merge_into_patient(source_id: str, target_id: str) -> bool:
    """
    Merge all rows from source_id profile into target_id profile,
    then delete the source profile. Used when a misspelled name
    created a duplicate patient that should be the same person.
    Returns True on success.
    """
    source_path = STORE_DIR / f"{source_id}.csv"
    target_path = STORE_DIR / f"{target_id}.csv"
    if not source_path.exists() or not target_path.exists():
        return False
    source_df = pd.read_csv(source_path)
    target_df = pd.read_csv(target_path)
    # Update patient_id in source rows to match target
    source_df["patient_id"] = target_id
    source_df["patient_name"] = target_df["patient_name"].iloc[0]
    combined = pd.concat([target_df, source_df], ignore_index=True)
    # Drop exact duplicates (same report_date + test_name)
    combined = combined.drop_duplicates(subset=["report_date", "test_name"], keep="first")
    combined.to_csv(target_path, index=False)
    source_path.unlink()
    return True


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