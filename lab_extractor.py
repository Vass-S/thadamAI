"""
Longitudinal Biomarker Intelligence Platform v5
Robust extraction + longitudinal trends + patient profiles

v5 changes (OCR logic is COMPLETELY UNCHANGED from v4):
  - Lab-specific extraction profiles (Kauvery, HiTech, Metropolis, Generic)
    stored in data/lab_profiles/<lab_id>.json — auto-detected per PDF
  - Kauvery profile handles:
      "Patient Name : Mr. Vijey Kumar K B"  (name on own line)
      "Age / Gender : 39/Years/Male"        (separate age/gender line)
      "Report Date : 19/01/2026 04:50 PM"   (DD/MM/YYYY with time)
      10^6/µL, 10^3/µL, g/dL, mg/L         (extended unit map)
      "(ABBREV) Test Name" prefix stripping
      Structured "Name  Result  Unit  Ref Range" table columns
  - HiTech/Metropolis/Generic profiles — wrap existing v4 patterns
  - Profiles persist to data/lab_profiles/*.json; unit strings accumulate
    so each upload teaches the system about that lab's format
  - Free-text extract_biomarkers() UNCHANGED (used as fallback + supplement)
  - All OCR imports, threshold, page loop — EXACTLY as in v4
"""

import re
import json
import hashlib
import pdfplumber
import pandas as pd
from pathlib import Path
from datetime import datetime

# ── OCR fallback — UNCHANGED FROM v4 ─────────────────────────────────────────
try:
    from pdf2image import convert_from_path as _pdf2img
    import pytesseract as _tess
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR     = Path(__file__).parent
DATA_DIR     = BASE_DIR / "data"
STORE_DIR    = DATA_DIR / "patient_profiles"
DICT_PATH    = DATA_DIR / "Biomarker_dictionary_csv.csv"
PROFILES_DIR = DATA_DIR / "lab_profiles"

STORE_DIR.mkdir(parents=True, exist_ok=True)
PROFILES_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# LAB PROFILES
# Each profile lives in data/lab_profiles/<lab_id>.json.
# On first use the builtin defaults are used and the file is written, then
# unit strings seen in real reports accumulate automatically.
# ═══════════════════════════════════════════════════════════════════════════════

_BUILTIN_PROFILES = {

    "kauvery": {
        "detect_keywords": [
            "kauvery", "kauvery hospital", "kauvery reference laboratory",
            "kauvery medical centre",
        ],
        "metadata_patterns": {
            # pdfplumber may collapse Kauvery's two-column header into single lines.
            # Patterns use lookahead stops (Order, Report, 2+ spaces, newline).
            "name": [
                # "Patient Name : Mr. Vijey Kumar K B   Order No : ..."
                r"Patient\s*Name\s*[:\-]\s*(?:Mr\.|Mrs\.|Ms\.|Dr\.)?\s*([\w][\w\s]+?)(?=\s{2,}|\s+Order\b|\s+Age\s*/|\n)",
                # Fallback: title prefix
                r"(?:Mr\.|Mrs\.|Ms\.|Dr\.)\s+([\w]+(?:\s+[\w]+){0,5})(?=\s{2,}|\s+Order|\s+Age\s*/|\s*\n|\s+\d)",
            ],
            "age": [
                # "Age / Gender : 39/Years/Male"  OR  "Age / Gender : 39/Male"  (Years optional)
                r"Age\s*/\s*(?:Gender|Sex)\s*[:\-]\s*(\d+)",
                # "Age : 39"
                r"Age\s*[:\-]\s*(\d+)",
            ],
            "gender": [
                # "Age / Gender : 39/Years/Male"  (Years optional, M/F or Male/Female)
                r"Age\s*/\s*(?:Gender|Sex)\s*[:\-]\s*\d+\s*/?\s*(?:Years?|Yrs?)?\s*/?\s*(Male|Female|M|F)\b",
                # "Gender : Male"  or  "Sex : M"
                r"(?:Gender|Sex)\s*[:\-]\s*(Male|Female|M|F)",
                # Bare word fallback — appears near the Age line
                r"\b(Male|Female)\b",
            ],
            "date": [
                # "Report Date : 19/01/2026 04:50 PM"
                r"Report\s*Date\s*[:\-]\s*(\d{1,2}/\d{1,2}/\d{4})",
                r"Collected\s*Date\s*[:\-]\s*(\d{1,2}/\d{1,2}/\d{4})",
                r"Order\s*Date\s*[:\-]\s*(\d{1,2}/\d{1,2}/\d{4})",
                r"(\d{2}/\d{2}/\d{4})",
            ],
        },
        "date_formats": ["%d/%m/%Y", "%m/%d/%Y"],
        "unit_fixes": {
            "10^6/ul": "10^6/µL", "10^6/µl": "10^6/µL",
            "10^3/ul": "10^3/µL", "10^3/µl": "10^3/µL",
            "g/dl": "g/dL", "mg/l": "mg/L", "mg/dl": "mg/dL",
            "fl": "fL", "pg": "pg", "mmol/l": "mmol/L", "umol/l": "µmol/L",
        },
        "test_name_transforms": [
            (r"^\([A-Z0-9\-]+\)\s*", ""),
            (r"\s*Method\s*:.*$", ""),
            (r"\s*\*+\s*$", ""),
        ],
        "table_structure": {"has_table": True,
                            "col_order": ["test_name", "result", "unit", "reference_range"]},
        "section_headers": [
            "Haematology", "Clinical chemistry", "SEROLOGY",
            "Biochemistry", "Urine Analysis", "Microbiology",
            "Complete Blood Count", "CBC", "Lipid Profile",
        ],
    },

    "hitech": {
        "detect_keywords": [
            "hitech", "hi tech", "hitech diagnostics", "hi-tech",
            "hitech reference", "hi tech reference",
        ],
        "metadata_patterns": {
            "name": [
                r"Patient\s*[:\-]\s*(?:[A-Z]\d+\s+)?(?:Mr\.|Mrs\.|Ms\.)?\s*([\w\s]+?)\s*\(\d+\s*/\s*[MF]\)",
                r"(?:Mr\.|Mrs\.|Ms\.)\s+([\w]+(?:\s+\w+)?)\s*(?:\n|$|Reference|VID)",
            ],
            "age": [
                r"Patient\s*[:\-]\s*.*?\((\d+)\s*/\s*[MF]\)",
                r"Age\s*[:\-]\s*(\d+)",
            ],
            "gender": [
                r"Patient\s*[:\-]\s*.*?\(\d+\s*/\s*([MF])\)",
                r"Sex\s*[:\-]\s*(Male|Female|M|F)",
            ],
            "date": [
                r"(?:Reported\s+On|Report\s+Date|Collected\s+On)\s*[:\-]\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
                r"SID\s+Date\s*[:\-]\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
                r"(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
            ],
        },
        "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y", "%d/%m/%y"],
        "unit_fixes": {},
        "test_name_transforms": [],
        "table_structure": {"has_table": False, "col_order": []},
        "section_headers": [],
    },

    "metropolis": {
        "detect_keywords": [
            "metropolis", "metropolis healthcare", "metropolis labs",
            "metropolis health services",
        ],
        "metadata_patterns": {
            "name": [
                r"(?:Mr\.|Mrs\.|Ms\.)\s+([\w]+(?:\s+[\w]+){0,4})\s*(?:\n|$|Reference|VID|Patient)",
                r"Patient\s*Name\s*[:\-]\s*(?:Mr\.|Mrs\.|Ms\.)?\s*([\w\s]+?)(?:\n|$|Age|Sex)",
            ],
            "age":    [r"Age\s*[:\-]\s*(\d+)"],
            "gender": [r"Sex\s*[:\-]\s*(Male|Female|M|F)"],
            "date": [
                r"(?:Reported\s+On|Report\s+Date|Collected\s+On|Collection\s+Date)\s*[:\-]\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
                r"(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
            ],
        },
        "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y"],
        "unit_fixes": {},
        "test_name_transforms": [],
        "table_structure": {"has_table": False, "col_order": []},
        "section_headers": [],
    },

    "generic": {
        "detect_keywords": [],
        "metadata_patterns": {
            "name": [
                # Kauvery-style: stop at 'Order' (pdfplumber collapses columns to 1 space)
                r"Patient\s*Name\s*[:\-]\s*(?:Mr\.|Mrs\.|Ms\.|Dr\.)?\s*([\w][\w\s]+?)(?:\s+Order\b|\s+Age\s*/\s*Gender|\s{2,}|\n)",
                # HiTech-style with age/gender in parens
                r"Patient\s*[:\-]\s*(?:[A-Z]\d+\s+)?(?:Mr\.|Mrs\.|Ms\.)?\s*([\w\s]+?)\s*\(\d+\s*/\s*[MF]\)",
                # Title-based
                r"(?:Mr\.|Mrs\.|Ms\.|Dr\.)\s+([\w]+(?:\s+[\w]+){0,5})(?=\s+Order|\s+Age\s*/|\s*\n|\s{2,}|\s+\d)",
            ],
            "age": [
                r"Age\s*/\s*(?:Gender|Sex)\s*[:\-]\s*(\d+)",
                r"Patient\s*[:\-]\s*.*?\((\d+)\s*/\s*[MF]\)",
                r"Age\s*[:\-]\s*(\d+)",
            ],
            "gender": [
                r"Age\s*/\s*(?:Gender|Sex)\s*[:\-]\s*\d+\s*/?\s*(?:Years?|Yrs?)?\s*/?\s*(Male|Female|M|F)\b",
                r"Patient\s*[:\-]\s*.*?\(\d+\s*/\s*([MF])\)",
                r"(?:Sex|Gender)\s*[:\-]\s*(Male|Female|M|F)",
                r"\b(Male|Female)\b",
            ],
            "date": [
                r"Report\s*Date\s*[:\-]\s*(\d{1,2}/\d{1,2}/\d{4})",
                r"Collected\s*Date\s*[:\-]\s*(\d{1,2}/\d{1,2}/\d{4})",
                r"(?:Reported\s+On|Report\s+Date|Collected\s+On|Collection\s+Date)\s*[:\-]\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
                r"SID\s+Date\s*[:\-]\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
                r"(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
            ],
        },
        "date_formats": ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y", "%d/%m/%y"],
        "unit_fixes": {
            "10^6/ul": "10^6/µL", "10^6/µl": "10^6/µL",
            "10^3/ul": "10^3/µL", "10^3/µl": "10^3/µL",
            "g/dl": "g/dL", "mg/l": "mg/L", "mg/dl": "mg/dL", "fl": "fL",
        },
        "test_name_transforms": [
            (r"^\([A-Z0-9\-]+\)\s*", ""),
            (r"\s*Method\s*:.*$", ""),
            (r"\s*\*+\s*$", ""),
        ],
        "table_structure": {"has_table": False, "col_order": []},
        "section_headers": [],
    },
}


def detect_lab(text: str) -> str:
    lower = text.lower()
    for lab_id, profile in _BUILTIN_PROFILES.items():
        if lab_id == "generic":
            continue
        for kw in profile.get("detect_keywords", []):
            if kw in lower:
                return lab_id
    return "generic"


def _load_profile(lab_id: str) -> dict:
    path    = PROFILES_DIR / f"{lab_id}.json"
    builtin = _BUILTIN_PROFILES.get(lab_id, _BUILTIN_PROFILES["generic"]).copy()
    if path.exists():
        try:
            with open(path) as f:
                saved = json.load(f)
            if saved.get("unit_fixes"):
                merged = dict(builtin.get("unit_fixes", {}))
                merged.update(saved["unit_fixes"])
                builtin["unit_fixes"] = merged
        except Exception:
            pass
    builtin["lab_id"] = lab_id
    return builtin


def _save_profile(lab_id: str, profile: dict) -> None:
    path = PROFILES_DIR / f"{lab_id}.json"
    try:
        with open(path, "w") as f:
            json.dump({"unit_fixes": profile.get("unit_fixes", {})}, f, indent=2)
    except Exception:
        pass


# ─────────────────────────────────────────────
# ALIASES & EXTRA BIOMARKERS
# ─────────────────────────────────────────────

EXTRA_ALIASES = {
    "Vitamin B12":                ["vitamin b 12", "vitamin b12"],
    "Vitamin D (25-OH)":          ["vitamin d (25-oh)", "25 hydroxy (oh) vit d", "25-oh vitamin d",
                                   "vitamin d", "25 oh vitamin d"],
    "Folic Acid":                 ["folic acid", "folate", "folic acid (serum)"],
    "Copper":                     ["copper"],
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
    "Total Cholesterol":          ["total cholesterol", "cholesterol total", "cholesterol"],
    "HDL Cholesterol":            ["hdl cholesterol", "hdl-c", "hdl", "high density lipoprotein"],
    "LDL Cholesterol":            ["ldl cholesterol", "ldl-c", "ldl", "low density lipoprotein"],
    "Triglycerides":              ["triglycerides", "tg", "trigs", "triglyceride"],
    "VLDL Cholesterol":           ["vldl cholesterol", "vldl-c", "vldl", "very low density lipoprotein"],
    "Non HDL Cholesterol":        ["non hdl cholesterol", "non-hdl cholesterol", "non hdl-c",
                                   "non hdl", "non-hdl"],
    "APO Lipoprotein A1":         ["apo lipoprotein a1", "apo a1", "apolipoprotein a1"],
    "APO Lipoprotein B":          ["apo lipoprotein b", "apolipoproteins b", "apo b", "apolipoprotein b"],
    "Lipoprotein(a)":             ["lipoprotein a ( lp a)", "lipoprotein(a)", "lp(a)", "lipoprotein a"],
    "Testosterone (Total)":       ["testosterone (total)", "testosterone", "total testosterone"],
    "Free Testosterone":          ["free testosterone", "testosterone free"],
    "DHEA Sulphate":              ["dhea sulphate", "dheas", "dhea-s", "dehydroepiandrosterone sulphate"],
    "DHEA":                       ["dhea", "dehydroepiandrosterone"],
    "TSH":                        ["tsh 3rd generation (hs tsh)", "tsh (hs tsh)", "hs tsh",
                                   "tsh 3rd generation", "tsh- 3rd generation (hs tsh)", "tsh"],
    "Free T3":                    ["free t3", "free t 3", "ft3", "free  t3"],
    "Free T4":                    ["free t4", "free t 4", "ft4", "free  t4"],
    "LH":                         ["lh", "luteinizing hormone", "luteinising hormone"],
    "FSH":                        ["fsh", "follicle stimulating hormone"],
    "Prolactin":                  ["prolactin"],
    "Estradiol":                  ["estradiol", "oestradiol", "e2"],
    "Progesterone":               ["progesterone"],
    "Cortisol (AM)":              ["cortisol ( am)", "cortisol (am)", "cortisol"],
    "Growth Hormone":             ["growth hormone", "gh", "hgh"],
    "IGF-I":                      ["igf - i", "igf i", "igf-1", "igf1", "igf i (somatomedin c)"],
    "AST (SGOT)":                 ["s.g.o.t. (ast)", "sgot (ast)", "sgot", "ast",
                                   "aspartate aminotransferase"],
    "ALT (SGPT)":                 ["s.g.p.t. (alt)", "sgpt (alt)", "sgpt", "alt",
                                   "alanine aminotransferase"],
    "Alkaline Phosphatase":       ["alkaline phosphatase", "alp", "alk phosphatase"],
    "Gamma GT":                   ["gamma gt ( ggtp)", "gamma gt (ggtp)", "ggt", "ggtp",
                                   "gamma glutamyl transferase", "gamma glutamyl transpeptidase",
                                   "gamma-glutamyl transferase"],
    "Bilirubin (Total)":          ["bilirubin - total", "bilirubin total", "total bilirubin"],
    "Bilirubin (Direct)":         ["bilirubin - direct", "bilirubin direct", "direct bilirubin"],
    "Bilirubin (Indirect)":       ["bilirubin - indirect", "bilirubin indirect", "indirect bilirubin"],
    "Total Protein":              ["total proteins", "total protein"],
    "Albumin":                    ["albumin", "serum albumin"],
    "Globulin":                   ["globulin", "total globulin"],
    "A/G Ratio":                  ["a/g ratio", "albumin globulin ratio", "ag ratio"],
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
    "MCV":                        ["mcv", "mean corpuscular volume", "mean cell volume",
                                   "mean corpuscular volume (mcv)"],
    "MCH":                        ["mch", "mean corpuscular hemoglobin",
                                   "mean corpuscular haemoglobin", "mean cell hemoglobin",
                                   "(mch) mean corpuscular haemoglobin",
                                   "(mch) mean corpuscular hemoglobin",
                                   "mch mean corpuscular haemoglobin"],
    "MCHC":                       ["mchc", "mean corpuscular hemoglobin concentration",
                                   "mean cell hemoglobin concentration",
                                   "(mchc) mean corpuscular haemoglobin concentration",
                                   "mchc mean corpuscular haemoglobin concentration"],
    "RDW-CV":                     ["rdw-cv", "rdw cv", "rdw", "red cell distribution width",
                                   "rdw - cv", "red blood cell distribution width"],
    "Neutrophil":                 ["neutrophil", "neutrophils", "neutrophil %",
                                   "neutrophils %", "polymorphonuclears", "pmn"],
    "Lymphocyte":                 ["lymphocyte", "lymphocytes", "lymphocyte %", "lymphocytes %"],
    "Monocyte":                   ["monocyte", "monocytes", "monocyte %", "monocytes %"],
    "Eosinophil":                 ["eosinophil", "eosinophils", "eosinophil %", "eosinophils %"],
    "Basophil":                   ["basophil", "basophils", "basophil %", "basophils %"],
    "Absolute Neutrophil Count":  ["absolute neutrophil count", "abs. neutrophil count",
                                   "abs neutrophil count", "absolute neutrophils", "anc",
                                   "neutrophil - absolute", "neutrophils absolute",
                                   "absolute neutrophil count (anc)"],
    "Absolute Lymphocyte Count":  ["absolute lymphocyte count", "abs. lymphocyte count",
                                   "abs lymphocyte count", "absolute lymphocytes", "alc",
                                   "lymphocyte - absolute", "lymphocytes absolute",
                                   "absolute lymphocyte count (alc)"],
    "Absolute Monocyte Count":    ["absolute monocyte count", "abs. monocyte count",
                                   "abs monocyte count", "absolute monocytes", "amc",
                                   "monocyte - absolute", "monocytes absolute",
                                   "absolute monocyte count (amc)"],
    "Absolute Eosinophil Count":  ["absolute eosinophil count", "abs. eosinophil count",
                                   "abs eosinophil count", "absolute eosinophils", "aec",
                                   "eosinophil - absolute", "eosinophils absolute",
                                   "absolute eosinophil count (aec)"],
    "Absolute Basophil Count":    ["absolute basophil count", "abs. basophil count",
                                   "abs basophil count", "absolute basophils", "abc",
                                   "basophil - absolute", "basophils absolute",
                                   "absolute basophil count (abc)"],
    "ESR":                        ["esr", "erythrocyte sedimentation rate", "sedimentation rate"],
    "hsCRP":                      ["hscrp", "hs-crp", "hs crp", "c reactive protein (hs)",
                                   "high sensitivity crp", "high sensitivity c reactive protein"],
    "C Reactive Protein":         ["c reactive protein", "crp", "c reactive protein (crp)"],
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
    "fl": "fL", "pg": "pg",
    "mu/100ul": "mU/100uL", "mu/ml": "mU/mL",
    "%": "%",
}

_UNIT_RE = (
    r'(mg\/dl|mg\/l|pg\/ml|pg\/dl|ng\/ml|ng\/dl'
    r'|ug\/dl|microgm\/dl|microgm\/ml'
    r'|u\/l|iu\/l|miu\/l|miu\/ml|uiu\/ml|\xb5iu\/ml|\xb5iu\/l'
    r'|gm\/dl|g\/dl'
    r'|10\^6\/\xb5l|10\^3\/\xb5l|10\^6\/ul|10\^3\/ul'
    r'|mmol\/l|umol\/l|nmol\/l'
    r'|mu\/100ul|mu\/ml'
    r'|fl|\xb5g\/dl|\xb5g\/ml|%)'
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
    if s.startswith(">="):  return float(s[2:]), None
    if s.startswith("<="):  return None, float(s[2:])
    if s.startswith(">"):   return float(s[1:]), None
    if s.startswith("<"):   return None, float(s[1:])
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


def normalize_unit(unit: str, lab_unit_fixes: dict = None) -> str:
    raw = str(unit).strip()
    low = raw.lower().replace(" ", "")
    if lab_unit_fixes:
        for k, v in lab_unit_fixes.items():
            if low == k.lower().replace(" ", ""):
                return v
    return _UNIT_MAP.get(low, raw)


# ─────────────────────────────────────────────
# PROFILE-AWARE METADATA EXTRACTION
# ─────────────────────────────────────────────

def _try_patterns(text: str, patterns: list) -> str | None:
    for pattern in patterns:
        try:
            m = re.search(pattern, text, re.I)
            if m:
                return m.group(1).strip()
        except re.error:
            pass
    return None


def _extract_kauvery_age_gender(text: str) -> tuple:
    """
    Dedicated extractor for Kauvery's 'Age / Gender : 39/Years/Male' line.
    Returns (age_int_or_None, gender_str_or_empty).
    Handles all real-world pdfplumber output variants including:
      - spaces/slashes between tokens
      - Years/Yrs optional
      - Male/Female or M/F
      - merged columns (trailing Report Date text)
      - non-breaking spaces and unicode variants
    """
    age   = None
    gender = ""

    # Normalise: replace unicode spaces/colons to ASCII
    clean = text.replace("\xa0", " ").replace("\uff1a", ":").replace("|", "/")

    # Strategy 1: structured Age/Gender line
    # Matches: "Age / Gender : 39/Years/Male" with any whitespace/slash variation
    age_gender_line = re.search(
        r"Age\s*/\s*(?:Gender|Sex)\s*[:\-]\s*(\d{1,3})\s*/?\s*(?:Years?|Yrs?)?\s*/?\s*(Male|Female|M|F)\b",
        clean, re.I
    )
    if age_gender_line:
        try:
            age = int(age_gender_line.group(1))
        except (ValueError, TypeError):
            pass
        g = age_gender_line.group(2).upper()
        gender = "M" if g in ("M", "MALE") else "F" if g in ("F", "FEMALE") else ""
        return age, gender

    # Strategy 2: age only from Age/Gender line (gender on next scan)
    age_only = re.search(
        r"Age\s*/\s*(?:Gender|Sex)\s*[:\-]\s*(\d{1,3})",
        clean, re.I
    )
    if age_only:
        try:
            age = int(age_only.group(1))
        except (ValueError, TypeError):
            pass

    # Fallback age: "Age : 39" standalone
    if age is None:
        m = re.search(r"\bAge\s*[:\-]\s*(\d{1,3})\b", clean, re.I)
        if m:
            try:
                age = int(m.group(1))
            except (ValueError, TypeError):
                pass

    # Strategy 3: gender from any clear indicator in the text
    for pat in [
        r"(?:Gender|Sex)\s*[:\-]\s*(Male|Female|M|F)\b",
        r"/\s*(Male|Female)\b",
        r"\b(Male|Female)\b",
        r"\b([MF])\s*/\s*\d",   # "M/39" format (reversed)
    ]:
        m = re.search(pat, clean, re.I)
        if m:
            g = m.group(1).upper()
            gender = "M" if g in ("M", "MALE") else "F" if g in ("F", "FEMALE") else ""
            if gender:
                break

    return age, gender


def _parse_date(date_str: str, fmts: list) -> str:
    date_part = re.split(r'\s+\d{1,2}:\d{2}', date_str)[0].strip()
    for fmt in fmts:
        try:
            return datetime.strptime(date_part, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def extract_metadata(text: str, profile: dict = None) -> dict:
    """
    Extract patient metadata using lab-specific profile patterns.
    Handles Kauvery, HiTech, Metropolis and generic formats.
    Returns dict: name, gender, date, age, phone, lab_id.

    For Kauvery reports: uses dedicated _extract_kauvery_age_gender()
    which handles all real-world pdfplumber output variants.
    """
    if profile is None:
        lab_id  = detect_lab(text)
        profile = _load_profile(lab_id)

    lab_id = profile.get("lab_id", "generic")
    meta = {
        "name": "", "gender": "", "date": "",
        "age": None, "phone": "",
        "lab_id": lab_id,
    }
    pats = profile.get("metadata_patterns", {})

    # ── Name ──────────────────────────────────────────────────────────
    raw_name = _try_patterns(text, pats.get("name", []))
    if raw_name:
        raw_name = re.sub(r'\b(Mr|Mrs|Ms|Dr|Miss)\.?\s*', '', raw_name, flags=re.I)
        raw_name = re.sub(r'\b[A-Z]\d+\b', '', raw_name)
        meta["name"] = re.sub(r'\s+', ' ', raw_name).strip().upper()

    # ── Age + Gender ───────────────────────────────────────────────────
    # For Kauvery: use the dedicated extractor which handles all variants.
    # For other labs: use profile patterns, then fall back to Kauvery extractor.
    if lab_id == "kauvery":
        kauv_age, kauv_gender = _extract_kauvery_age_gender(text)
        if kauv_age is not None:
            meta["age"] = kauv_age
        if kauv_gender:
            meta["gender"] = kauv_gender
    else:
        raw_age = _try_patterns(text, pats.get("age", []))
        if raw_age:
            try:
                meta["age"] = int(raw_age)
            except ValueError:
                pass

        raw_gender = _try_patterns(text, pats.get("gender", []))
        if raw_gender:
            val = raw_gender.strip().upper()
            if val in ("MALE", "M"):
                meta["gender"] = "M"
            elif val in ("FEMALE", "F"):
                meta["gender"] = "F"

    # If age/gender still missing, try the Kauvery extractor as universal fallback
    if meta["age"] is None or not meta["gender"]:
        fb_age, fb_gender = _extract_kauvery_age_gender(text)
        if meta["age"] is None and fb_age is not None:
            meta["age"] = fb_age
        if not meta["gender"] and fb_gender:
            meta["gender"] = fb_gender

    # ── Date ──────────────────────────────────────────────────────────
    raw_date = _try_patterns(text, pats.get("date", []))
    if raw_date:
        meta["date"] = _parse_date(raw_date, profile.get("date_formats", _DATE_FMTS))

    # ── Phone (same across all labs) ──────────────────────────────────
    m = re.search(r"(?:Tel|Ph|Phone|Mobile)\s*(?:No\.?)?\s*[:\-]?\s*\+?(\d[\d\s\-]{9,})", text, re.I)
    if m:
        digits = re.sub(r'\D', '', m.group(1))
        meta["phone"] = digits[-10:] if len(digits) >= 10 else digits

    return meta


# ─────────────────────────────────────────────
# STRUCTURED TABLE EXTRACTION  (Kauvery-style)
# ─────────────────────────────────────────────

def _clean_test_name(raw: str, transforms: list) -> str:
    s = raw.strip()
    for pattern, replacement in transforms:
        s = re.sub(pattern, replacement, s, flags=re.I).strip()
    return s


def _match_alias(test_name_raw: str) -> str | None:
    lower = test_name_raw.lower().strip()
    if lower in _ALIAS_MAP:
        return _ALIAS_MAP[lower]
    for alias in _ALL_ALIASES:
        if alias in lower:
            return _ALIAS_MAP[alias]
    return None


_TABLE_SKIP = re.compile(
    r'\b(reference range|investigation name|result|method|interpretation|'
    r'sample collected|validated by|approved by|end of report|please correlate|'
    r'printed on|page \d|haematology|clinical chemistry|serology|biochemistry|'
    r'urine analysis|microbiology|cbc|complete blood count)\b',
    re.I
)


def extract_from_table(pages_text: list, profile: dict, gender: str = "") -> list:
    """
    Extract biomarkers from structured lab table columns (Kauvery-style).
    Lines look like: "Haemoglobin (Hb)         14.2       g/dL    13.0-17.0"
    """
    results    = []
    seen       = set()
    transforms = profile.get("test_name_transforms", [])
    unit_fixes = profile.get("unit_fixes", {})

    unit_pat = re.compile(
        r'(10\^[36]/[µu]L?|g/dL|g/dl|fL|fl|pg|%|U/L|u/l|'
        r'mmol/L|mmol/l|mg/dL|mg/dl|mg/L|mg/l|'
        r'mIU/L|miu/l|µIU/mL|IU/L|iu/l|ng/mL|ng/ml|ng/dL|ng/dl|'
        r'µg/dL|µg/mL|10\^6/µL|10\^3/µL|10\^6/ul|10\^3/ul)',
        re.I
    )

    for page_text in pages_text:
        lines = [l.strip() for l in page_text.split("\n") if l.strip()]
        i = 0
        while i < len(lines):
            line = lines[i]
            if _TABLE_SKIP.search(line):
                i += 1
                continue

            # Match: <test name><2+ spaces><number><optional spaces><unit>
            result_match = re.search(r'\s{2,}([<>]?\s*\d+(?:\.\d+)?)\s{0,6}', line)
            if result_match:
                raw_val = result_match.group(1).replace(" ", "").lstrip("<>")
                try:
                    value = float(raw_val)
                except ValueError:
                    i += 1
                    continue

                if not (0 < value < 1_000_000):
                    i += 1
                    continue

                # Unit: look immediately after the number
                rest      = line[result_match.end():]
                unit_m    = unit_pat.match(rest.strip().split()[0] if rest.strip() else "")
                raw_unit  = unit_m.group(0) if unit_m else ""
                unit      = normalize_unit(raw_unit, unit_fixes)

                test_part     = line[:result_match.start()].strip()
                test_name_raw = _clean_test_name(test_part, transforms)
                canonical     = _match_alias(test_name_raw)

                if canonical and canonical not in seen:
                    seen.add(canonical)
                    results.append({
                        "test_name": canonical,
                        "value":     value,
                        "unit":      unit,
                        "status":    flag_status(canonical, value, unit, gender),
                    })
                i += 1
                continue

            # No inline number — check next line for standalone value
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                num_m = re.match(r'^([<>]?\s*\d+(?:\.\d+)?)\s*([\w\^/µ%]*)$', next_line)
                if num_m and not _TABLE_SKIP.search(next_line):
                    raw_val  = num_m.group(1).replace(" ", "").lstrip("<>")
                    raw_unit = num_m.group(2) or ""
                    try:
                        value = float(raw_val)
                    except ValueError:
                        i += 1
                        continue
                    if 0 < value < 1_000_000:
                        test_name_raw = _clean_test_name(line, transforms)
                        unit          = normalize_unit(raw_unit, unit_fixes)
                        canonical     = _match_alias(test_name_raw)
                        if canonical and canonical not in seen:
                            seen.add(canonical)
                            results.append({
                                "test_name": canonical,
                                "value":     value,
                                "unit":      unit,
                                "status":    flag_status(canonical, value, unit, gender),
                            })
                    i += 2
                    continue

            i += 1
    return results


# ─────────────────────────────────────────────
# FREE-TEXT EXTRACTION  (UNCHANGED from v4)
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


def extract_biomarkers(text, gender="", lab_unit_fixes: dict = None):
    """Original free-text alias-based extraction — UNCHANGED from v4."""
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
                        unit_line  = re.sub(r'\s+', ' ', lines[i + lookahead]).strip()
                        unit_match = re.match(r'^' + _UNIT_RE + r'$', unit_line, re.I)
                        if unit_match:
                            found = (found[0], normalize_unit(unit_match.group(1), lab_unit_fixes))
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
    Returns (DataFrame, raw_text).

    1. pdfplumber — collect per-page text.
    2. OCR fallback if < 80 words  [UNCHANGED from v4].
    3. Detect lab → load profile.
    4. Profile-aware metadata extraction.
    5. Table-mode extraction first (Kauvery), then free-text for anything missed.
    6. Accumulate unit strings into profile JSON for future reports.
    """
    pdf_path = Path(pdf_path)

    pages_text = []
    full_text  = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            pages_text.append(t)
            full_text += t + "\n"

    ocr_used = False

    # ── OCR fallback — UNCHANGED FROM v4 ──────────────────────────────────
    if _OCR_AVAILABLE and len(full_text.split()) < 80:
        try:
            images    = _pdf2img(str(pdf_path), dpi=300)
            ocr_pages = [_tess.image_to_string(img, config="--psm 6") for img in images]
            ocr_text  = "\n".join(ocr_pages)
            if len(ocr_text.split()) > len(full_text.split()):
                full_text  = ocr_text
                pages_text = ocr_pages
                ocr_used   = True
        except Exception:
            pass

    lab_id  = detect_lab(full_text)
    profile = _load_profile(lab_id)

    if verbose:
        print(f"  Lab detected: {lab_id}")

    meta = extract_metadata(full_text, profile=profile)
    pid  = make_patient_id(meta)

    seen_canonical: set = set()
    results: list = []

    if profile.get("table_structure", {}).get("has_table"):
        for r in extract_from_table(pages_text, profile, gender=meta.get("gender", "")):
            seen_canonical.add(r["test_name"])
            results.append(r)

    for r in extract_biomarkers(
        full_text,
        gender=meta.get("gender", ""),
        lab_unit_fixes=profile.get("unit_fixes", {}),
    ):
        if r["test_name"] not in seen_canonical:
            seen_canonical.add(r["test_name"])
            results.append(r)

    if verbose:
        mode = " [OCR]" if ocr_used else ""
        print(f"  {pdf_path.name}{mode}: {len(results)} tests | {meta.get('name','?')} | {meta.get('date','?')}")

    if not results:
        return pd.DataFrame(), full_text

    df = pd.DataFrame(results)
    df["patient_id"]    = pid
    df["patient_name"]  = meta["name"]
    df["gender"]        = meta.get("gender", "")
    df["age_at_test"]   = meta.get("age", "")
    df["report_date"]   = meta["date"]
    df["source_file"]   = pdf_path.name
    df["file_hash"]     = file_hash(pdf_path)
    df["ocr_extracted"] = ocr_used
    df["lab_id"]        = lab_id

    if meta.get("age") and meta.get("date"):
        try:
            df["birth_year"] = int(meta["date"][:4]) - int(meta["age"])
        except (ValueError, TypeError):
            df["birth_year"] = None
    else:
        df["birth_year"] = None

    # Accumulate unit strings for this lab
    unit_fixes = profile.get("unit_fixes", {})
    for _, row in df.iterrows():
        raw_unit = str(row.get("unit", "")).strip()
        key = raw_unit.lower().replace(" ", "")
        if raw_unit and key not in unit_fixes:
            unit_fixes[key] = raw_unit
    profile["unit_fixes"] = unit_fixes
    _save_profile(lab_id, profile)

    return df, full_text


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
    path = STORE_DIR / f"{patient_id}.csv"
    if not path.exists():
        return False
    df = pd.read_csv(path)
    df["patient_name"] = new_name.strip().upper()
    df.to_csv(path, index=False)
    return True


def merge_into_patient(source_id: str, target_id: str) -> bool:
    src_path = STORE_DIR / f"{source_id}.csv"
    tgt_path = STORE_DIR / f"{target_id}.csv"
    if not src_path.exists() or not tgt_path.exists():
        return False
    try:
        src = pd.read_csv(src_path)
        tgt = pd.read_csv(tgt_path)
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
    for idx in df[mask].index:
        gender = str(df.at[idx, "gender"]) if "gender" in df.columns else ""
        unit   = str(df.at[idx, "unit"])
        df.at[idx, "status"] = flag_status(test_name, new_value, unit, gender)
    df.to_csv(path, index=False)
    return True


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
# PATIENT ID
# ─────────────────────────────────────────────

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