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
    "Vitamin B12":                ["vitamin b 12", "vitamin b12"],
    "Vitamin D (25-OH)":          ["vitamin d (25-oh)", "25 hydroxy (oh) vit d", "25-oh vitamin d",
                                   "vitamin d", "25 oh vitamin d"],
    "Folic Acid":                 ["folic acid", "folate", "folic acid (serum)"],
    "Copper":                     ["copper"],

    # Metabolic / renal
    "Urea (Serum)":               ["urea - serum", "urea", "blood urea", "blood urea nitrogen", "bun"],
    "Creatinine (Serum)":         ["creatinine - serum", "creatinine", "serum creatinine"],
    "Uric Acid":                  ["uric acid", "serum uric acid"],
    "Glucose (Fasting)":          ["glucose (fasting)", "glucose fasting (plasma-f,hexokinase)",
                                   "glucose fasting", "fasting blood sugar", "fbs", "fasting glucose",
                                   "blood glucose fasting"],
    "Glucose (Post Prandial 2hr)":["pp glucose", "post prandial glucose", "pbg",
                                   "glucose post prandial", "pp blood sugar",
                                   "2hr pp glucose", "2 hr pp glucose"],
    "HbA1c":                      ["hb a1c", "hba1c- glycated haemoglobin",
                                   "hba1c- glycated haemoglobin (hplc)", "glycated haemoglobin",
                                   "hba1c- glycated haemoglobin, blood by hplc method",
                                   "glycohaemoglobin", "glycosylated haemoglobin"],

    # Lipids
    "Total Cholesterol":          ["total cholesterol", "cholesterol total", "cholesterol"],
    "HDL Cholesterol":            ["hdl cholesterol", "hdl-c", "hdl", "high density lipoprotein"],
    "LDL Cholesterol":            ["ldl cholesterol", "ldl-c", "ldl", "low density lipoprotein"],
    "Triglycerides":              ["triglycerides", "tg", "trigs", "triglyceride"],
    "VLDL Cholesterol":           ["vldl cholesterol", "vldl-c", "vldl",
                                   "very low density lipoprotein"],
    "Non HDL Cholesterol":        ["non hdl cholesterol", "non-hdl cholesterol", "non hdl-c",
                                   "non hdl", "non-hdl"],
    "APO Lipoprotein A1":         ["apo lipoprotein a1", "apo a1", "apolipoprotein a1"],
    "APO Lipoprotein B":          ["apo lipoprotein b", "apolipoproteins b", "apo b",
                                   "apolipoprotein b"],
    "Lipoprotein(a)":             ["lipoprotein a ( lp a)", "lipoprotein(a)", "lp(a)",
                                   "lipoprotein a"],

    # Hormones - androgens
    "Testosterone (Total)":       ["testosterone (total)", "testosterone", "total testosterone"],
    "Free Testosterone":          ["free testosterone", "testosterone free"],
    "DHEA Sulphate":              ["dhea sulphate", "dheas", "dhea-s", "dehydroepiandrosterone sulphate"],
    "DHEA":                       ["dhea", "dehydroepiandrosterone"],

    # Hormones - thyroid
    "TSH":                        ["tsh 3rd generation (hs tsh)", "tsh (hs tsh)", "hs tsh",
                                   "tsh 3rd generation", "tsh- 3rd generation (hs tsh)", "tsh"],
    "Free T3":                    ["free t3", "free t 3", "ft3", "free  t3"],
    "Free T4":                    ["free t4", "free t 4", "ft4", "free  t4"],

    # Hormones - pituitary / reproductive
    "LH":                         ["lh", "luteinizing hormone", "luteinising hormone"],
    "FSH":                        ["fsh", "follicle stimulating hormone"],
    "Prolactin":                  ["prolactin"],
    "Estradiol":                  ["estradiol", "oestradiol", "e2"],
    "Progesterone":               ["progesterone"],

    # Hormones - adrenal / growth
    "Cortisol (AM)":              ["cortisol ( am)", "cortisol (am)", "cortisol"],
    "Growth Hormone":             ["growth hormone", "gh", "hgh"],
    "IGF-I":                      ["igf - i", "igf i", "igf-1", "igf1", "igf i (somatomedin c)"],

    # Liver
    "AST (SGOT)":                 ["s.g.o.t. (ast)", "sgot (ast)", "sgot", "ast", "aspartate aminotransferase"],
    "ALT (SGPT)":                 ["s.g.p.t. (alt)", "sgpt (alt)", "sgpt", "alt", "alanine aminotransferase"],
    "Alkaline Phosphatase":       ["alkaline phosphatase", "alp", "alk phosphatase"],
    "Gamma GT":                   ["gamma gt ( ggtp)", "gamma gt (ggtp)", "ggt", "ggtp",
                                   "gamma glutamyl transferase", "gamma glutamyl transpeptidase"],
    "Bilirubin (Total)":          ["bilirubin - total", "bilirubin total", "total bilirubin"],
    "Bilirubin (Direct)":         ["bilirubin - direct", "bilirubin direct", "direct bilirubin"],
    "Bilirubin (Indirect)":       ["bilirubin - indirect", "bilirubin indirect", "indirect bilirubin"],
    "Total Protein":              ["total proteins", "total protein"],
    "Albumin":                    ["albumin", "serum albumin"],
    "Globulin":                   ["globulin", "total globulin"],
    "A/G Ratio":                  ["a/g ratio", "albumin globulin ratio", "ag ratio"],

    # CBC — main counts
    "Haemoglobin":                ["haemoglobin", "hemoglobin", "hb", "hgb",
                                   "haemoglobin (hb)", "hemoglobin (hb)"],
    "Haematocrit":                ["haematocrit", "hematocrit", "pcv", "packed cell volume"],
    "Total RBC Count":            ["total rbc count", "rbc count", "rbc", "red blood cell count",
                                   "red cell count", "erythrocyte count"],
    "Total WBC Count":            ["total wbc count", "wbc count", "wbc", "total leucocyte count",
                                   "tlc", "leukocyte count", "white blood cell count",
                                   "total white blood cell count"],
    "Platelet Count":             ["platelet count", "platelets", "plt",
                                   "thrombocyte count", "platelet"],
    "MCV":                        ["mcv", "mean corpuscular volume", "mean cell volume"],
    "MCH":                        ["mch", "mean corpuscular hemoglobin",
                                   "mean corpuscular haemoglobin", "mean cell hemoglobin"],
    "MCHC":                       ["mchc", "mean corpuscular hemoglobin concentration",
                                   "mean cell hemoglobin concentration"],
    "RDW-CV":                     ["rdw-cv", "rdw cv", "rdw", "red cell distribution width"],

    # CBC differentials (%)
    "Neutrophil":                 ["neutrophil", "neutrophils", "neutrophil %",
                                   "neutrophils %", "polymorphonuclears", "pmn"],
    "Lymphocyte":                 ["lymphocyte", "lymphocytes", "lymphocyte %", "lymphocytes %"],
    "Monocyte":                   ["monocyte", "monocytes", "monocyte %", "monocytes %"],
    "Eosinophil":                 ["eosinophil", "eosinophils", "eosinophil %", "eosinophils %"],
    "Basophil":                   ["basophil", "basophils", "basophil %", "basophils %"],

    # CBC — absolute counts
    "Absolute Neutrophil Count":  ["absolute neutrophil count", "abs. neutrophil count",
                                   "abs neutrophil count", "absolute neutrophils", "anc",
                                   "neutrophil - absolute", "neutrophils absolute"],
    "Absolute Lymphocyte Count":  ["absolute lymphocyte count", "abs. lymphocyte count",
                                   "abs lymphocyte count", "absolute lymphocytes", "alc",
                                   "lymphocyte - absolute", "lymphocytes absolute"],
    "Absolute Monocyte Count":    ["absolute monocyte count", "abs. monocyte count",
                                   "abs monocyte count", "absolute monocytes", "amc",
                                   "monocyte - absolute", "monocytes absolute"],
    "Absolute Eosinophil Count":  ["absolute eosinophil count", "abs. eosinophil count",
                                   "abs eosinophil count", "absolute eosinophils", "aec",
                                   "eosinophil - absolute", "eosinophils absolute"],
    "Absolute Basophil Count":    ["absolute basophil count", "abs. basophil count",
                                   "abs basophil count", "absolute basophils", "abc",
                                   "basophil - absolute", "basophils absolute"],

    # Inflammation / cardiac
    "ESR":                        ["esr", "erythrocyte sedimentation rate", "sedimentation rate"],
    "hsCRP":                      ["hscrp", "hs-crp", "hs crp", "c reactive protein (hs)",
                                   "high sensitivity crp", "high sensitivity c reactive protein"],
    "C Reactive Protein":         ["c reactive protein", "crp"],

    # Serology
    "Anti-Sperm Antibody":        ["anti sperm antibody", "anti-sperm antibody"],
    "Dengue NS1 Antigen":         ["dengue ns1 antigen", "dengue ns1", "ns1 antigen"],
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
    gender = meta.get("gender", "").upper()
    name   = _clean_name(meta.get("name", ""))
    phone  = re.sub(r"\D", "", meta.get("phone", ""))[-10:]
    age    = meta.get("age")

    real_words = [w for w in name.split() if len(w) >= 2]

    if len(real_words) >= 2:
        key = f"FULLNAME|{'_'.join(real_words)}|{gender}"
        return "P" + hashlib.sha256(key.encode()).hexdigest()[:8].upper()

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
    if not STORE_DIR.exists():
        return None
    for csv_file in STORE_DIR.glob("*.csv"):
        try:
            df = pd.read_csv(csv_file, nrows=1)
            if df.empty:
                continue
            stored_name   = _clean_name(str(df["patient_name"].iloc[0]))
            stored_gender = str(df.get("gender", pd.Series([""])).iloc[0]).upper()
            if stored_gender != gender:
                continue
            stored_first = stored_name.split()[0] if stored_name.split() else ""
            if stored_first != first_name.upper():
                continue
            if len(first_name) >= 4:
                return csv_file.stem
        except Exception:
            continue
    return None


# ─────────────────────────────────────────────
# DUPLICATE DETECTION
# ─────────────────────────────────────────────

def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_duplicate_file(path: Path) -> bool:
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
    snippet = re.sub(r'\(cid:\d+\)', '', snippet)
    m = re.search(
        r'[:\|\s]*([<>]?\s*\d+(?:\.\d+)?)' + r'\s*' + _UNIT_RE,
        snippet, re.IGNORECASE
    )
    if not m:
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

            if not found:
                for lookahead in range(1, 3):
                    if i + lookahead < len(lines):
                        next_line = re.sub(r'\s+', ' ', lines[i + lookahead]).strip()
                        if re.search(r'\b(upto|less than|more than|deficient|normal\s*:|method\s*:|specimen\s*:)\b', next_line, re.I):
                            continue
                        found = find_value_in_text(next_line, 0)
                        if found:
                            break

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

def process_pdf(pdf_path, verbose=False):
    """
    Extract biomarkers + metadata from a PDF lab report.
    Returns (DataFrame, raw_text). DataFrame is empty if extraction fails.
    """
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
        return pd.DataFrame(), text

    df = pd.DataFrame(results)
    df["patient_id"]   = pid
    df["patient_name"] = meta["name"]
    df["gender"]       = meta.get("gender", "")
    df["age_at_test"]  = meta.get("age", "")
    df["report_date"]  = meta["date"]
    df["source_file"]  = pdf_path.name
    df["file_hash"]    = file_hash(pdf_path)

    if meta.get("age") and meta.get("date"):
        df["birth_year"] = int(meta["date"][:4]) - int(meta["age"])
    else:
        df["birth_year"] = None

    return df, text


def save_report(df: pd.DataFrame) -> None:
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


def load_history(patient_id: str) -> pd.DataFrame:
    path = STORE_DIR / f"{patient_id}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")
    if "birth_year" in df.columns:
        birth_years = pd.to_numeric(df["birth_year"], errors="coerce").dropna()
        if not birth_years.empty:
            birth_year = int(birth_years.min())
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
    path = STORE_DIR / f"{patient_id}.csv"
    if path.exists():
        path.unlink()
        return True
    return False


def delete_report_by_date(patient_id: str, report_date: str) -> bool:
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
# PATIENT MANAGEMENT
# ─────────────────────────────────────────────

def rename_patient(patient_id: str, new_name: str) -> bool:
    """Rename all rows for a patient to new_name (stored as UPPER). Returns True on success."""
    path = STORE_DIR / f"{patient_id}.csv"
    if not path.exists():
        return False
    df = pd.read_csv(path)
    df["patient_name"] = new_name.strip().upper()
    df.to_csv(path, index=False)
    return True


def merge_into_patient(source_id: str, target_id: str) -> bool:
    """
    Merge all reports from source_id into target_id, then delete source_id.
    Duplicate (test_name, report_date) rows are dropped (target wins).
    Returns True on success.
    """
    src_path = STORE_DIR / f"{source_id}.csv"
    tgt_path = STORE_DIR / f"{target_id}.csv"
    if not src_path.exists() or not tgt_path.exists():
        return False
    try:
        src = pd.read_csv(src_path)
        tgt = pd.read_csv(tgt_path)
        # Rewrite source rows to carry the target patient identity
        src["patient_id"]   = target_id
        src["patient_name"] = tgt["patient_name"].iloc[0]
        merged = pd.concat([tgt, src], ignore_index=True)
        merged.drop_duplicates(subset=["test_name", "report_date"], keep="first", inplace=True)
        merged.sort_values(["test_name", "report_date"]).to_csv(tgt_path, index=False)
        src_path.unlink()
        return True
    except Exception:
        return False


def patch_record(patient_id: str, report_date: str, test_name: str,
                 new_value: float, new_unit: str = "") -> bool:
    """
    Overwrite the value (and optionally unit) for one specific
    (patient, report_date, test_name) record, then recompute status.
    Returns True if a matching row was found and updated.
    """
    path = STORE_DIR / f"{patient_id}.csv"
    if not path.exists():
        return False
    df = pd.read_csv(path)
    mask = (
        (df["report_date"].astype(str).str[:10] == str(report_date)[:10]) &
        (df["test_name"] == test_name)
    )
    if not mask.any():
        return False
    df.loc[mask, "value"] = new_value
    if new_unit:
        df.loc[mask, "unit"] = new_unit
    # Recompute status for the patched row
    for idx in df[mask].index:
        gender = str(df.at[idx, "gender"]) if "gender" in df.columns else ""
        unit   = str(df.at[idx, "unit"])
        df.at[idx, "status"] = flag_status(test_name, new_value, unit, gender)
    df.to_csv(path, index=False)
    return True


# ─────────────────────────────────────────────
# TRENDS & TIMESERIES
# ─────────────────────────────────────────────

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
        return pd.DataFrame(columns=["test_name", "first_date", "first_value",
                                     "latest_date", "latest_value", "unit",
                                     "change_%", "trend", "latest_status", "n_reports"])
    return pd.DataFrame(rows).sort_values("change_%", key=abs, ascending=False)


def get_test_timeseries(history: pd.DataFrame, test_name: str) -> pd.DataFrame:
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