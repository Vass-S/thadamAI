"""
Longitudinal Biomarker Intelligence Platform — v5
Streamlit Web App

Changes in v5:
  - Unified colour palette (green/amber/red semantic zones) via CSS variables
  - Chart reference bands: green = normal, red = high zone, amber = low zone
  - Educational callouts rendered as styled cards, not plain captions
  - Summary grid: 4 cards (total / ok / out-of-range / critical) + progress bar
  - Results table: CRITICAL → HIGH → LOW → normal sort order
  - Trends table: date-centric with column_config number formatting
  - clean_unit() helper sanitises µ corruption and NaN in one place
  - bm_lookup() wraps dictionary access so render functions stay clean
  - os import moved to top-level (was re-imported on every page render)
  - _get_api_key() cached so it is not re-read on every Streamlit rerun

Fixes in v5.1:
  - Removed duplicate st.download_button in Patient Profiles tab1
    (caused StreamlitDuplicateElementId crash that blocked Trends charts)
  - Fixed expander icon "keyboard_double_arrow_right" text appearing on hover
    by loading Material Symbols font + hiding the SVG sibling span correctly
"""

import os
import tempfile
import atexit
from pathlib import Path

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from lab_extractor import (
    process_pdf, save_report, load_history, generate_trends,
    get_test_timeseries, list_patients, is_duplicate_file,
    delete_patient, delete_report_by_date, rename_patient,
    merge_into_patient, patch_record, STORE_DIR,
)
from llm_verifier import (
    verify_with_llm, build_diff, apply_corrections,
    get_metadata_corrections,
    save_pending_review, load_pending_reviews, delete_pending_review,
)

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Biomarker Intelligence",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# PALETTE  — Clean clinical white design
# ─────────────────────────────────────────────
BG       = "#f8f8f8"
SURFACE  = "#ffffff"
SURFACE2 = "#f4f4f6"
BORDER   = "#e8e8ee"
ACCENT   = "#4ecdc4"
BLUE     = "#74b9e8"
PURPLE   = "#c084fc"
ORANGE   = "#f97b5a"
GREEN    = "#4ecdc4"
AMBER    = "#f5a623"
RED      = "#f97b5a"
CRIT     = "#e53e3e"
TEXT     = "#1a1a2e"
MUTED    = "#8a8aaa"
LIGHT    = "#f0f0f8"
GREEN_Z  = "rgba(78,205,196,0.08)"
AMBER_Z  = "rgba(245,166,35,0.08)"
RED_Z    = "rgba(249,123,90,0.08)"

# ─────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=DM+Mono:wght@400;500&display=swap');

/* ── Base ── */
html, body, .stApp {{
  background-color: {BG} !important;
  color: {TEXT} !important;
  font-family: 'DM Sans', sans-serif !important;
}}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {{
  background-color: {SURFACE} !important;
  border-right: 1px solid {BORDER} !important;
}}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] div {{
  color: {TEXT} !important;
}}

/* ── Main content background ── */
[data-testid="stAppViewContainer"],
[data-testid="stAppViewBlockContainer"],
[data-testid="stMainBlockContainer"],
section[data-testid="stMain"] {{
  background-color: {BG} !important;
}}

/* ── Typography ── */
p, label, h1, h2, h3, h4, h5, h6 {{
  color: {TEXT} !important;
  font-family: 'DM Sans', sans-serif !important;
}}

/* ── Tabs — fix overlap by ensuring overflow visible and no position conflicts ── */
.stTabs [data-baseweb="tab-list"] {{
  border-bottom: 1px solid {BORDER} !important;
  background: transparent !important;
  gap: 0 !important;
  overflow: visible !important;
}}
.stTabs [data-baseweb="tab"] {{
  background: transparent !important;
  border-radius: 0 !important;
  color: {MUTED} !important;
  font-size: 0.82rem !important;
  font-weight: 500 !important;
  padding: 0.6rem 1.2rem !important;
  border-bottom: 2px solid transparent !important;
  overflow: visible !important;
  position: static !important;
}}
.stTabs [aria-selected="true"] {{
  color: {TEXT} !important;
  border-bottom: 2px solid {ACCENT} !important;
}}
.stTabs [data-baseweb="tab-panel"] {{
  background: transparent !important;
  padding-top: 1rem !important;
}}

/* ── Expander ── */
[data-testid="stExpander"] summary {{
  background-color: {SURFACE} !important;
  border: 1px solid {BORDER} !important;
  border-radius: 10px !important;
  color: {TEXT} !important;
}}
[data-testid="stExpander"] > div:last-child {{
  background-color: {SURFACE} !important;
  border: 1px solid {BORDER} !important;
  border-top: none !important;
  border-radius: 0 0 10px 10px !important;
}}

/* ── Buttons ── */
.stButton > button {{
  background-color: {TEXT} !important;
  border: none !important;
  color: #fff !important;
  font-size: 0.82rem !important;
  border-radius: 10px !important;
  padding: 0.45rem 1.2rem !important;
  transition: background 0.15s !important;
}}
.stButton > button:hover {{
  background-color: {ACCENT} !important;
}}
.stButton > button[kind="primary"] {{
  background-color: {ACCENT} !important;
}}
.stDownloadButton > button {{
  background: transparent !important;
  border: 1px solid {BORDER} !important;
  color: {MUTED} !important;
  font-size: 0.75rem !important;
  border-radius: 8px !important;
  box-shadow: none !important;
}}
.stDownloadButton > button:hover {{
  color: {TEXT} !important;
  background: {LIGHT} !important;
}}

/* ── Inputs ── */
.stSelectbox [data-baseweb="select"] > div,
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
textarea {{
  background-color: {SURFACE} !important;
  border: 1px solid {BORDER} !important;
  color: {TEXT} !important;
  border-radius: 10px !important;
}}
div[data-baseweb="option"] {{
  background-color: {SURFACE} !important;
  color: {TEXT} !important;
}}
div[data-baseweb="option"]:hover {{
  background-color: {LIGHT} !important;
}}

/* ── File uploader ── */
.stFileUploader > div {{
  background: {SURFACE} !important;
  border: 2px dashed {BORDER} !important;
  border-radius: 16px !important;
}}

/* ── Dataframe / charts ── */
.stDataFrame {{
  border: 1px solid {BORDER} !important;
  border-radius: 12px !important;
  overflow: hidden !important;
}}
.stPlotlyChart {{
  border: 1px solid {BORDER} !important;
  border-radius: 16px !important;
  overflow: hidden !important;
  background: {SURFACE} !important;
}}

/* ── Alerts ── */
div[data-testid="stAlert"] {{
  border-radius: 12px !important;
}}

/* ── Progress bar ── */
.stProgress > div > div > div > div {{
  background: {ACCENT} !important;
  border-radius: 4px !important;
}}

/* ── Tags (multiselect) ── */
div[data-baseweb="tag"] {{
  background: rgba(78,205,196,0.12) !important;
  border-radius: 6px !important;
}}

/* ── Hide only deploy/footer chrome, leave sidebar toggle alone ── */
#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}
.stDeployButton {{ display: none !important; }}

/* ── Custom layout classes ── */
.bip-header {{
  display: flex; align-items: center; gap: 14px;
  padding-bottom: 1.5rem; margin-bottom: 2rem;
  border-bottom: 1px solid {BORDER};
}}
.bip-header h1 {{
  font-size: 1.55rem !important; font-weight: 700 !important;
  color: {TEXT} !important; margin: 0 !important;
}}
.bip-header .sub {{
  font-family: 'DM Mono', monospace; font-size: 0.6rem; letter-spacing: 3px;
  text-transform: uppercase; color: {MUTED};
  background: {LIGHT}; border: 1px solid {BORDER};
  padding: 4px 12px; border-radius: 20px;
}}
.section-label {{
  font-family: 'DM Mono', monospace; font-size: 0.57rem; letter-spacing: 3px;
  text-transform: uppercase; color: {MUTED}; margin: 1.5rem 0 0.75rem;
}}
.patient-card {{
  background: {SURFACE}; border: 1px solid {BORDER};
  border-radius: 16px; padding: 1.5rem 2rem; margin-bottom: 1.75rem;
  display: grid; grid-template-columns: repeat(4,1fr); gap: 1.5rem;
  box-shadow: 0 2px 16px rgba(0,0,0,0.04);
}}
.patient-card .field label {{
  font-family: 'DM Mono', monospace; font-size: 0.55rem; letter-spacing: 2.5px;
  text-transform: uppercase; color: {MUTED}; display: block; margin-bottom: 6px;
}}
.patient-card .field value {{ font-size: 1.05rem; font-weight: 600; color: {TEXT}; }}
.section-label {{ font-family: 'DM Mono', monospace; font-size: 0.57rem; letter-spacing: 3px;
  text-transform: uppercase; color: {MUTED}; margin: 1.5rem 0 0.75rem; }}
.callout {{
  background: {LIGHT}; border: 1px solid {BORDER};
  border-left: 3px solid {ACCENT}; border-radius: 0 12px 12px 0;
  padding: 0.85rem 1.2rem; margin-top: 0.5rem; font-size: 0.82rem; line-height: 1.75; color: {MUTED};
}}
.callout b {{ color: {TEXT}; }}
.callout-title {{
  font-family: 'DM Mono', monospace; font-size: 0.55rem; letter-spacing: 2px;
  text-transform: uppercase; color: {ACCENT}; margin-bottom: 5px;
}}
.range-legend {{ display: inline-flex; align-items: center; gap: 6px; font-size: 0.7rem; color: {MUTED}; margin-bottom: 0.4rem; }}
.dot {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; }}
</style>
""", unsafe_allow_html=True)

# JS: Force light color-scheme
st.markdown("""
<script>
(function() {
  try {
    var meta = document.querySelector('meta[name="color-scheme"]');
    if (!meta) { meta = document.createElement('meta'); meta.name = 'color-scheme'; document.head.appendChild(meta); }
    meta.content = 'light';
    var origMM = window.matchMedia;
    window.matchMedia = function(q) {
      if (q && q.includes('prefers-color-scheme')) {
        return { matches: q.includes('light'), media: q, addListener:function(){}, removeListener:function(){}, addEventListener:function(){}, removeEventListener:function(){} };
      }
      return origMM.apply(this, arguments);
    };
    document.documentElement.style.setProperty('background-color','#f7f8fc','important');
    if (document.body) document.body.style.setProperty('background-color','#f7f8fc','important');
  } catch(e) {}
})();
</script>
""", unsafe_allow_html=True)

def _parse_range(s):
    if pd.isna(s):
        return None, None
    s = str(s).strip()
    if not s or s.lower() == "nan":
        return None, None
    try:
        if s.startswith("<="):  return None, float(s[2:])
        if s.startswith("<"):   return None, float(s[1:])
        if s.startswith(">="):  return float(s[2:]), None
        if s.startswith(">"):   return float(s[1:]), None
        for sep in ["\u2013", "-"]:
            if sep in s:
                a, b = s.split(sep, 1)
                return float(a.strip()), float(b.strip())
        v = float(s)
        return v, v
    except (ValueError, IndexError):
        return None, None


@st.cache_data
def load_biomarker_dictionary():
    for path in ["data/Biomarker_dictionary_csv.csv", "Biomarker_dictionary_csv.csv"]:
        try:
            df = pd.read_csv(path, encoding="latin1")
            break
        except FileNotFoundError:
            continue
    else:
        return pd.DataFrame()

    if "canonical_name" not in df.columns:
        return pd.DataFrame()

    for src_col, (mn, mx) in {
        "normal_range":    ("normal_min",    "normal_max"),
        "optimal_range":   ("optimal_min",   "optimal_max"),
        "high_risk_range": ("high_risk_min", "high_risk_max"),
        "diseased_range":  ("diseased_min",  "diseased_max"),
    }.items():
        if src_col in df.columns:
            parsed = df[src_col].apply(lambda x: pd.Series(_parse_range(x), index=[mn, mx]))
            df[mn], df[mx] = parsed[mn], parsed[mx]
        else:
            df[mn] = df[mx] = None

    for col in ["short_description", "interpretation_summary", "category",
                "related_conditions", "common_panels"]:
        if col not in df.columns:
            df[col] = None

    return df.set_index("canonical_name")


biomarker_dictionary = load_biomarker_dictionary()


@st.cache_data
def _build_alias_index() -> dict:
    idx = {}
    if biomarker_dictionary.empty:
        return idx

    for canonical in biomarker_dictionary.index:
        idx[canonical.lower().strip()] = canonical
        row = biomarker_dictionary.loc[canonical]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        aliases_raw = row.get("aliases", "")
        if pd.notna(aliases_raw) and str(aliases_raw).strip():
            for a in str(aliases_raw).split(","):
                a = a.strip().lower()
                if a:
                    idx[a] = canonical

    # Aliases are fully defined in Biomarker_dictionary_csv.csv
    return idx


def bm_lookup(test_name: str) -> dict:
    if biomarker_dictionary.empty:
        return {}
    if test_name in biomarker_dictionary.index:
        row = biomarker_dictionary.loc[test_name]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        return row.to_dict()
    alias_idx = _build_alias_index()
    key = test_name.lower().strip()
    canonical = alias_idx.get(key)
    if canonical and canonical in biomarker_dictionary.index:
        row = biomarker_dictionary.loc[canonical]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        return row.to_dict()
    key_clean = key.replace("(", "").replace(")", "").replace(".", "").replace("-", " ")
    for canonical in biomarker_dictionary.index:
        c_clean = canonical.lower().replace("(", "").replace(")", "").replace(".", "").replace("-", " ")
        if key_clean == c_clean:
            row = biomarker_dictionary.loc[canonical]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            return row.to_dict()
    for canonical in biomarker_dictionary.index:
        c_lower = canonical.lower()
        if key in c_lower or c_lower in key:
            row = biomarker_dictionary.loc[canonical]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            return row.to_dict()
    return {}


# ─────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────

def clean_unit(u) -> str:
    s = str(u).strip()
    if s in ("nan", "None", "NaN", ""):
        return ""
    return (s.replace("Âµ", "µ")
             .replace("Ã‚", "")
             .replace("\ufffd", "µ"))


def safe_name(history: pd.DataFrame) -> str:
    n = history["patient_name"].iloc[0]
    return str(n).replace(" ", "_") if pd.notna(n) else "patient"


def _status_sort(s: str) -> int:
    if "CRITICAL" in str(s): return 0
    if "HIGH"     in str(s): return 1
    if "LOW"      in str(s): return 2
    return 3


def _point_color(status: str) -> str:
    s = str(status)
    if "CRITICAL" in s: return CRIT
    if "HIGH"     in s: return ORANGE
    if "LOW"      in s: return PURPLE
    return ACCENT


def status_pill(status: str) -> str:
    s = str(status)
    if "CRITICAL" in s:
        return f'<span style="background:{CRIT}22;color:{CRIT};font-weight:600;padding:2px 8px;border-radius:20px;font-size:0.78rem">{s}</span>'
    if "HIGH" in s:
        return f'<span style="background:{ORANGE}22;color:{ORANGE};font-weight:600;padding:2px 8px;border-radius:20px;font-size:0.78rem">{s}</span>'
    if "LOW" in s:
        return f'<span style="background:{PURPLE}22;color:{PURPLE};font-weight:600;padding:2px 8px;border-radius:20px;font-size:0.78rem">{s}</span>'
    return f'<span style="background:{ACCENT}22;color:{ACCENT};font-weight:600;padding:2px 8px;border-radius:20px;font-size:0.78rem">{s or "Normal"}</span>'


_tmp_files: list[str] = []

def _make_tmp(data: bytes, suffix: str = ".pdf") -> Path:
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(data)
        path = f.name
    _tmp_files.append(path)
    return Path(path)

def _cleanup_tmp():
    for p in _tmp_files:
        try:
            os.unlink(p)
        except OSError:
            pass

atexit.register(_cleanup_tmp)


def get_snapshot(history: pd.DataFrame) -> pd.DataFrame:
    return (history.sort_values("report_date")
                   .groupby("test_name").last()
                   .reset_index())


# ─────────────────────────────────────────────
# RENDER: PATIENT CARD
# ─────────────────────────────────────────────

def render_patient_card(history: pd.DataFrame):
    name    = history["patient_name"].iloc[0]
    gender  = history["gender"].iloc[0]
    age_col = "current_age" if "current_age" in history.columns else "age_at_test"
    age_val = history[age_col].dropna()
    age_str = str(int(age_val.iloc[0])) if not age_val.empty else "—"
    dates   = history["report_date"].dropna()
    n       = len(dates.dt.strftime("%Y-%m-%d").unique()) if not dates.empty else 0
    last_dt = dates.max().strftime("%d %b %Y") if not dates.empty else "—"
    g_str   = "Male" if str(gender).upper() == "M" else "Female"

    st.markdown(f"""
    <div class="patient-card">
      <div class="field"><label>Patient</label><value>{name}</value></div>
      <div class="field"><label>Gender</label><value>{g_str}</value></div>
      <div class="field"><label>Age</label><value>{age_str}</value></div>
      <div class="field"><label>Reports</label><value>{n}  <span style="font-size:0.75rem;color:{MUTED};font-weight:400">· last {last_dt}</span></value></div>
    </div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# RENDER: RADIAL BIOMARKER OVERVIEW
# ─────────────────────────────────────────────

def render_radial_overview(snapshot: pd.DataFrame, filter_status: str = "all"):
    """
    Circular radial dashboard — 4 quadrant zones.
    Each biomarker dot is placed in the correct zone based on its actual value
    vs the reference ranges in the biomarker dictionary.

    Quadrant layout (SVG coords: 0°=right, 90°=down, clockwise):
      Top-right    (-45° → 45°)  = Optimal   (green)
      Bottom-right ( 45° →135°)  = Normal    (purple)
      Bottom-left  (135° →225°)  = High Risk (orange)
      Top-left     (225° →315°)  = Diseased  (red)

    Fixes vs previous version:
      - Canvas enlarged to 640×640 so outer labels are never clipped
      - Labels rendered OUTSIDE the grey circle, always visible
      - classify() uses pd.notna() to handle NaN from bm_lookup
      - Disease threshold logic corrected for HIGH and LOW results
      - Dot rows capped so dots never exceed R_OUTER
      - Label text corrected: "Diseased" not "Disease"
    """
    import math

    df = snapshot.copy()
    df["unit"] = df["unit"].apply(clean_unit)

    if filter_status == "critical":
        df = df[df["status"].str.contains("CRITICAL", na=False)]
    elif filter_status == "oor":
        df = df[df["status"].str.contains("HIGH|LOW", na=False)]
    elif filter_status == "normal":
        df = df[~df["status"].str.contains("HIGH|LOW|CRITICAL", na=False)]

    if len(df) == 0:
        st.info("No biomarkers match this filter.")
        return

    # ── helpers ────────────────────────────────────────────────────────────
    def _safe_float(v):
        """Convert to float, return None if not possible or NaN."""
        try:
            f = float(v)
            return None if math.isnan(f) else f
        except (TypeError, ValueError):
            return None

    # ── Classify each biomarker into a zone using real patient values ──────
    def classify(row):
        bm  = bm_lookup(row["test_name"])
        s   = str(row.get("status", ""))
        val = _safe_float(row["value"])
        if val is None:
            return "normal"

        # CRITICAL flag → always Diseased
        if "CRITICAL" in s:
            return "disease"

        if "HIGH" in s or "LOW" in s:
            # Check if value crosses into diseased threshold
            d_min = _safe_float(bm.get("diseased_min"))
            d_max = _safe_float(bm.get("diseased_max"))
            if "HIGH" in s and d_min is not None and val >= d_min:
                return "disease"
            if "LOW"  in s and d_max is not None and val <= d_max:
                return "disease"
            return "highrisk"

        # Normal status — check whether inside optimal range
        o_min = _safe_float(bm.get("optimal_min"))
        o_max = _safe_float(bm.get("optimal_max"))
        has_optimal = (o_min is not None or o_max is not None)
        if has_optimal:
            below = (o_min is not None and val < o_min)
            above = (o_max is not None and val > o_max)
            if not below and not above:
                return "optimal"
        return "normal"

    df["_zone"] = df.apply(classify, axis=1)

    groups = {z: df[df["_zone"] == z].reset_index(drop=True)
              for z in ("optimal", "normal", "highrisk", "disease")}

    n_total = len(df)

    # ── SVG canvas ─────────────────────────────────────────────────────────
    # Larger canvas (640) gives room for labels outside the grey circle
    W,  H  = 640, 640
    CX, CY = W / 2, H / 2

    R_INNER    = 95    # inner edge of dot track
    R_OUTER    = 240   # outer edge of dot track
    R_GREY     = 260   # grey background circle radius
    R_STEP     = 21    # radial gap between stacked dot rows
    DOT_R      = 7.5   # dot radius
    DOT_GAP    = 13    # minimum degrees between dots in a row

    # Pastel zone colours
    C = {
        "optimal":  "#6ecfaa",
        "normal":   "#b09fdc",
        "highrisk": "#f5a97b",
        "disease":  "#ef8080",
    }
    FILL = {
        "optimal":  "rgba(110,207,170,0.09)",
        "normal":   "rgba(176,159,220,0.09)",
        "highrisk": "rgba(245,169,123,0.09)",
        "disease":  "rgba(239,128,128,0.09)",
    }
    STROKE = {
        "optimal":  "rgba(110,207,170,0.40)",
        "normal":   "rgba(176,159,220,0.40)",
        "highrisk": "rgba(245,169,123,0.40)",
        "disease":  "rgba(239,128,128,0.40)",
    }

    # Each zone owns a 90° arc. Angles in standard SVG math coords
    # (0°=3 o'clock, increasing clockwise).
    ARCS = {
        "optimal":  (-45,  45),   # top-right
        "normal":   ( 45, 135),   # bottom-right
        "highrisk": (135, 225),   # bottom-left
        "disease":  (225, 315),   # top-left
    }

    # Label text, bisector angle, and display name for each zone
    # bisector = midpoint of arc in SVG degrees
    ZONE_META = {
        "optimal":  {"label": "Optimal",   "bisector":   0},
        "normal":   {"label": "Normal",    "bisector":  90},
        "highrisk": {"label": "High Risk", "bisector": 180},
        "disease":  {"label": "Diseased",  "bisector": 270},
    }

    def to_xy(deg, r):
        a = math.radians(deg)
        return CX + r * math.cos(a), CY + r * math.sin(a)

    def arc_d(r, a0, a1, steps=90):
        pts = []
        for i in range(steps + 1):
            a = a0 + (a1 - a0) * i / steps
            x, y = to_xy(a, r)
            pts.append(f"{'M' if i == 0 else 'L'}{x:.2f},{y:.2f}")
        return " ".join(pts)

    def sector_d(r_in, r_out, a0, a1, steps=80):
        outer, inner = [], []
        for i in range(steps + 1):
            t = a0 + (a1 - a0) * i / steps
            outer.append(to_xy(t, r_out))
            inner.append(to_xy(t, r_in))
        d = f"M{outer[0][0]:.2f},{outer[0][1]:.2f}"
        for x, y in outer[1:]:
            d += f" L{x:.2f},{y:.2f}"
        for x, y in reversed(inner):
            d += f" L{x:.2f},{y:.2f}"
        return d + " Z"

    # ── Compute dot positions from real patient data ────────────────────────
    def dot_positions(zone, zone_df):
        a0, a1 = ARCS[zone]
        n = len(zone_df)
        if n == 0:
            return []
        padding  = min(6, (a1 - a0) * 0.07)
        arc_lo   = a0 + padding
        arc_hi   = a1 - padding
        arc_span = arc_hi - arc_lo

        max_per_row = max(1, int(arc_span / DOT_GAP))
        dots = []

        for i, (_, row) in enumerate(zone_df.iterrows()):
            row_idx = i // max_per_row
            col_idx = i %  max_per_row
            cols    = min(max_per_row, n - row_idx * max_per_row)
            angle   = arc_lo + arc_span * col_idx / (cols - 1) if cols > 1 else (arc_lo + arc_hi) / 2
            r       = min(R_INNER + 28 + row_idx * R_STEP, R_OUTER - DOT_R - 2)
            x, y    = to_xy(angle, r)

            val_str = ""
            try:    val_str = f"{float(row['value']):.4g}"
            except: val_str = str(row.get("value", ""))
            unit_str   = str(row.get("unit", ""))
            status_str = str(row.get("status", "Normal") or "Normal")
            tooltip    = f"{row['test_name']} | {val_str} {unit_str} | {status_str}"
            dots.append({"x": x, "y": y, "tooltip": tooltip, "name": row["test_name"]})
        return dots

    all_dots = {z: dot_positions(z, groups[z]) for z in ARCS}

    # ── Build SVG ──────────────────────────────────────────────────────────
    P = []   # svg parts list

    # Root SVG — plain rect background (NOT border-radius:50%) so labels outside
    # the grey circle are still visible
    P.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'viewBox="0 0 {W} {H}" '
             f'style="display:block;margin:auto;background:#ffffff;'
             f'font-family:\'DM Sans\',Arial,sans-serif;">')

    P.append('<defs>'
             '<filter id="ds" x="-40%" y="-40%" width="180%" height="180%">'
             '<feDropShadow dx="0" dy="1.5" stdDeviation="2.5" flood-color="rgba(0,0,0,0.12)"/>'
             '</filter>'
             '</defs>')

    # White page background
    P.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')

    # Grey circle background
    P.append(f'<circle cx="{CX}" cy="{CY}" r="{R_GREY}" fill="#f2f2f5" stroke="none"/>')

    # Zone sector fills (subtle tint per quadrant)
    for z, (a0, a1) in ARCS.items():
        P.append(f'<path d="{sector_d(R_INNER-8, R_OUTER+18, a0, a1)}" '
                 f'fill="{FILL[z]}" stroke="{STROKE[z]}" stroke-width="0.5"/>')

    # Dashed concentric grid rings
    for r in [R_INNER + 5, R_INNER + 40, R_INNER + 75, R_INNER + 110, R_OUTER + 5]:
        P.append(f'<circle cx="{CX}" cy="{CY}" r="{r}" '
                 f'fill="none" stroke="rgba(150,150,170,0.22)" '
                 f'stroke-width="0.9" stroke-dasharray="4,5"/>')

    # Quadrant divider spokes (at 45°, 135°, 225°, 315°)
    for angle in [45, 135, 225, 315]:
        x1, y1 = to_xy(angle, R_INNER - 10)
        x2, y2 = to_xy(angle, R_OUTER + 20)
        P.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                 f'stroke="rgba(140,140,160,0.45)" stroke-width="0.9"/>')

    # Coloured outer arc accent per zone
    for z, (a0, a1) in ARCS.items():
        P.append(f'<path d="{arc_d(R_OUTER+12, a0, a1)}" '
                 f'fill="none" stroke="{STROKE[z]}" '
                 f'stroke-width="3" stroke-linecap="round"/>')

    # ── Dots (real patient biomarkers) ──────────────────────────────────────
    for z, dots in all_dots.items():
        for d in dots:
            P.append(
                f'<circle cx="{d["x"]:.2f}" cy="{d["y"]:.2f}" r="{DOT_R}" '
                f'fill="{C[z]}" stroke="white" stroke-width="2.2" '
                f'filter="url(#ds)" opacity="0.92">'
                f'<title>{d["tooltip"]}</title>'
                f'</circle>'
            )

    # ── Zone labels — placed OUTSIDE the grey circle, never clipped ─────────
    # bisector angle tells us which edge; we position text just beyond R_GREY
    for z, meta in ZONE_META.items():
        bis   = meta["bisector"]   # 0=right, 90=bottom, 180=left, 270=top
        label = meta["label"]
        col   = C[z]

        # Push label far enough past the grey circle edge
        r_lbl = R_GREY + 22

        # For two-word labels (High Risk) we use a tspan to split onto 2 lines
        # at left/right edges where vertical space is tight
        lx, ly = to_xy(bis, r_lbl)

        # Text anchor: left side → end, right side → start, top/bottom → middle
        if   bis == 0:   anchor, dy_off = "start",  0
        elif bis == 90:  anchor, dy_off = "middle",  0
        elif bis == 180: anchor, dy_off = "end",     0
        else:            anchor, dy_off = "middle",  0   # 270 = top

        # Split "High Risk" over two lines for the left label
        if " " in label:
            words = label.split()
            line1, line2 = words[0], " ".join(words[1:])
            P.append(
                f'<text text-anchor="{anchor}" '
                f'font-size="11" fill="{col}" font-weight="600" letter-spacing="0.3">'
                f'<tspan x="{lx:.1f}" y="{ly - 7:.1f}">{line1}</tspan>'
                f'<tspan x="{lx:.1f}" dy="14">{line2}</tspan>'
                f'</text>'
            )
        else:
            P.append(
                f'<text x="{lx:.1f}" y="{ly:.1f}" '
                f'text-anchor="{anchor}" dominant-baseline="middle" '
                f'font-size="11" fill="{col}" font-weight="600" letter-spacing="0.3">'
                f'{label}</text>'
            )

    # ── Centre white disc + number + "Biomarkers" ───────────────────────────
    P.append(f'<circle cx="{CX}" cy="{CY}" r="{R_INNER - 12}" '
             f'fill="white" stroke="rgba(190,190,210,0.5)" stroke-width="1.2"/>')

    P.append(f'<text x="{CX}" y="{CY - 10}" text-anchor="middle" dominant-baseline="middle" '
             f'font-size="54" font-weight="700" fill="#1a1a2e" letter-spacing="-2">'
             f'{n_total}</text>')

    P.append(f'<text x="{CX}" y="{CY + 30}" text-anchor="middle" dominant-baseline="middle" '
             f'font-size="12" font-weight="400" fill="#9090aa" letter-spacing="0.8">'
             f'Biomarkers</text>')

    P.append("</svg>")

    html = (
        '<div style="display:flex;justify-content:center;padding:8px 0;">'
        + "\n".join(P)
        + "</div>"
    )
    st.components.v1.html(html, height=H + 20, scrolling=False)


# ─────────────────────────────────────────────
# RENDER: SUMMARY CARDS
# ─────────────────────────────────────────────

def render_summary_cards(snapshot: pd.DataFrame):
    total    = len(snapshot)
    critical = snapshot["status"].str.contains("CRITICAL", na=False).sum()
    abnormal = snapshot["status"].str.contains("HIGH|LOW", na=False).sum()
    normal   = total - abnormal
    oor      = abnormal - critical
    pct_ok   = int(normal / total * 100) if total else 0
    bar_col  = ACCENT if pct_ok >= 80 else (AMBER if pct_ok >= 60 else ORANGE)

    st.markdown(f"""
    <div class="summary-grid">
      <div class="summary-card">
        <div class="num" style="color:{TEXT}">{total}</div>
        <div class="lbl">Total Tests</div>
      </div>
      <div class="summary-card">
        <div class="num" style="color:{ACCENT}">{normal}</div>
        <div class="lbl">Within Range</div>
      </div>
      <div class="summary-card">
        <div class="num" style="color:{ORANGE}">{oor}</div>
        <div class="lbl">Out of Range</div>
      </div>
      <div class="summary-card">
        <div class="num" style="color:{CRIT}">{critical}</div>
        <div class="lbl">Critical</div>
      </div>
    </div>
    <div style="margin-bottom:1.5rem">
      <div style="display:flex;justify-content:space-between;margin-bottom:6px">
        <span style="font-size:0.78rem;color:{MUTED}">Within-Range Score</span>
        <span style="font-size:0.82rem;font-weight:600;color:{bar_col}">{pct_ok}%</span>
      </div>
      <div style="background:{BORDER};border-radius:8px;height:6px">
        <div style="width:{pct_ok}%;height:100%;background:{bar_col};
               border-radius:8px;transition:width 0.6s ease"></div>
      </div>
    </div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# RENDER: RESULTS TABLE
# ─────────────────────────────────────────────

def render_results_table(snapshot: pd.DataFrame):
    df = snapshot.copy()
    df["_ord"] = df["status"].apply(_status_sort)
    df = df.sort_values(["_ord", "test_name"]).drop(columns=["_ord"])
    df["unit"] = df["unit"].apply(clean_unit)

    def fmt(v):
        try: return f"{float(v):.4g}"
        except: return str(v)

    def fmt_status(s):
        s = str(s) if pd.notna(s) else ""
        if "CRITICAL" in s: return f"🔴 {s}"
        if "HIGH"     in s: return f"🟠 {s}"
        if "LOW"      in s: return f"🟡 {s}"
        return f"🟢 Normal" if not s or s == "nan" else f"🟢 {s}"

    display = pd.DataFrame({
        "Test":   df["test_name"],
        "Value":  df["value"].apply(fmt),
        "Unit":   df["unit"],
        "Status": df["status"].apply(fmt_status),
    })

    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config={
            "Test":   st.column_config.TextColumn("Test",   width="large"),
            "Value":  st.column_config.TextColumn("Value",  width="small"),
            "Unit":   st.column_config.TextColumn("Unit",   width="small"),
            "Status": st.column_config.TextColumn("Status", width="medium"),
        },
    )


# ─────────────────────────────────────────────
# RENDER: TRENDS TABLE
# ─────────────────────────────────────────────

def render_trends_table(trends: pd.DataFrame):
    df = trends.copy()
    df["unit"] = df["unit"].apply(clean_unit)

    def fmt(v):
        try: return f"{float(v):.4g}"
        except: return str(v)

    def fmt_status(s):
        s = str(s) if pd.notna(s) else ""
        if "CRITICAL" in s: return f"🔴 {s}"
        if "HIGH"     in s: return f"🟠 {s}"
        if "LOW"      in s: return f"🟡 {s}"
        return f"🟢 Normal" if not s or s in ("—", "nan") else f"🟢 {s}"

    def fmt_dir(row):
        t   = str(row.get("trend", ""))
        pct = row.get("change_%", 0)
        try: pct = float(pct)
        except: pct = 0
        arrow = "↑" if pct > 0 else ("↓" if pct < 0 else "→")
        return f"{arrow} {abs(pct):.1f}%"

    display = pd.DataFrame({
        "Test":         df["test_name"],
        "From":         df["first_date"],
        "First Value":  df["first_value"].apply(fmt),
        "To":           df["latest_date"],
        "Latest Value": df["latest_value"].apply(fmt),
        "Unit":         df["unit"],
        "Change":       df.apply(fmt_dir, axis=1),
        "Status":       df["latest_status"].apply(fmt_status),
        "Reports":      df["n_reports"],
    })

    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config={
            "Test":         st.column_config.TextColumn("Test",         width="large"),
            "From":         st.column_config.TextColumn("From",         width="small"),
            "First Value":  st.column_config.TextColumn("First Value",  width="small"),
            "To":           st.column_config.TextColumn("To",           width="small"),
            "Latest Value": st.column_config.TextColumn("Latest Value", width="small"),
            "Unit":         st.column_config.TextColumn("Unit",         width="small"),
            "Change":       st.column_config.TextColumn("Δ",            width="small"),
            "Status":       st.column_config.TextColumn("Status",       width="medium"),
            "Reports":      st.column_config.NumberColumn("#",          width="small"),
        },
    )


# ─────────────────────────────────────────────
# RENDER: PILL SLIDER
# ─────────────────────────────────────────────

def render_pill_slider(value: float, n_min, o_min, n_max, o_max, unit: str, status: str) -> str:
    ref_lo = o_min if o_min is not None else n_min
    ref_hi = o_max if o_max is not None else n_max
    if o_min is not None and o_max is not None:
        optimal = (o_min + o_max) / 2
    elif o_max is not None:
        optimal = o_max
    elif o_min is not None:
        optimal = o_min
    else:
        optimal = None

    if ref_lo is None and ref_hi is None:
        return ""

    all_vals = [v for v in [value, ref_lo, ref_hi, n_min, n_max] if v is not None]
    if not all_vals:
        return ""

    span_lo = min(all_vals) * 0.7
    span_hi = max(all_vals) * 1.35
    span_lo = min(span_lo, value * 0.7) if value > 0 else span_lo - abs(value) * 0.3
    span_hi = max(span_hi, value * 1.35) if value > 0 else span_hi + abs(value) * 0.3
    if span_lo == span_hi:
        span_lo -= 1; span_hi += 1
    span = span_hi - span_lo

    def pct(v):
        return max(3, min(95, (v - span_lo) / span * 100))

    s = str(status)
    if   "CRITICAL" in s: dot_color = CRIT
    elif "HIGH"     in s: dot_color = ORANGE
    elif "LOW"      in s: dot_color = PURPLE
    else:                  dot_color = BLUE

    val_pct = pct(value)

    opt_html = ""
    if ref_lo is not None and ref_hi is not None:
        opt_l = pct(ref_lo); opt_r = pct(ref_hi)
        opt_html = (
            f'<div style="position:absolute;left:{opt_l}%;width:{opt_r-opt_l}%;'
            f'height:100%;background:rgba(78,205,196,0.15);'
            f'border:1.5px dashed {ACCENT};border-radius:20px;box-sizing:border-box"></div>'
        )
    elif ref_hi is not None:
        opt_r = pct(ref_hi)
        opt_html = (
            f'<div style="position:absolute;left:3%;width:{opt_r-3}%;'
            f'height:100%;background:rgba(78,205,196,0.12);'
            f'border:1.5px dashed {ACCENT};border-right:none;border-radius:20px 0 0 20px;box-sizing:border-box"></div>'
        )
    elif ref_lo is not None:
        opt_l = pct(ref_lo)
        opt_html = (
            f'<div style="position:absolute;left:{opt_l}%;width:{95-opt_l}%;'
            f'height:100%;background:rgba(78,205,196,0.12);'
            f'border:1.5px dashed {ACCENT};border-left:none;border-radius:0 20px 20px 0;box-sizing:border-box"></div>'
        )

    opt_label_html = ""
    if optimal is not None:
        opt_pct = pct(optimal)
        opt_str = f"< {optimal:.4g}" if (o_min is None and o_max is not None) else \
                  f"> {optimal:.4g}" if (o_min is not None and o_max is None) else \
                  f"{optimal:.4g}"
        opt_label_html = (
            f'<div style="position:absolute;bottom:-17px;left:{opt_pct}%;'
            f'transform:translateX(-50%);font-size:0.6rem;color:{ACCENT};'
            f'white-space:nowrap;font-weight:500">{opt_str}</div>'
        )

    val_str = f"{value:.4g}"

    html = f"""
    <div style="position:relative;margin-top:22px;margin-bottom:22px;padding:0 8px">
      <div style="position:relative;height:26px;background:{LIGHT};
                  border:1.5px dashed {BORDER};border-radius:20px;overflow:visible;
                  box-sizing:border-box">
        {opt_html}
        <div style="position:absolute;top:-18px;left:{val_pct}%;
                    transform:translateX(-50%);font-size:0.68rem;
                    font-weight:700;color:{dot_color};white-space:nowrap">{val_str}</div>
        <div style="position:absolute;top:50%;left:{val_pct}%;
                    transform:translate(-50%,-50%);
                    width:20px;height:20px;border-radius:50%;
                    background:{dot_color};border:3px solid {SURFACE};
                    box-shadow:0 2px 6px rgba(0,0,0,0.18);z-index:3"></div>
        {opt_label_html}
      </div>
    </div>"""
    return html


# ─────────────────────────────────────────────
# RENDER: BIOMARKER DETAIL CARDS
# ─────────────────────────────────────────────

def render_biomarker_cards(snapshot: pd.DataFrame, history: pd.DataFrame = None):
    df = snapshot.copy()
    df["_ord"] = df["status"].apply(_status_sort)
    df = df.sort_values(["_ord", "test_name"]).drop(columns=["_ord"])
    df["unit"] = df["unit"].apply(clean_unit)

    prev_values = {}
    if history is not None and not history.empty:
        sorted_hist = history.sort_values("report_date")
        dates = sorted_hist["report_date"].dt.strftime("%Y-%m-%d").unique()
        if len(dates) >= 2:
            prev_date = dates[-2]
            prev_df = sorted_hist[sorted_hist["report_date"].dt.strftime("%Y-%m-%d") == prev_date]
            for _, r in prev_df.iterrows():
                prev_values[r["test_name"]] = r["value"]

    def fmt(v):
        try: return f"{float(v):.4g}"
        except: return str(v)

    def _fmt_range(lo, hi) -> str:
        if lo is not None and hi is not None:
            return f"{lo:.4g} – {hi:.4g}"
        elif hi is not None:
            return f"< {hi:.4g}"
        elif lo is not None:
            return f"> {lo:.4g}"
        return "—"

    def _opt_target(o_min, o_max, n_min, n_max):
        if o_min is not None and o_max is not None:
            return (o_min + o_max) / 2
        elif o_max is not None:
            return o_max
        elif o_min is not None:
            return o_min
        elif n_min is not None and n_max is not None:
            return (n_min + n_max) / 2
        elif n_max is not None:
            return n_max
        elif n_min is not None:
            return n_min
        return None

    for _, row in df.iterrows():
        test   = row["test_name"]
        val    = row["value"]
        unit   = row["unit"]
        status = str(row.get("status", ""))
        bm     = bm_lookup(test)

        n_min = bm.get("normal_min")
        n_max = bm.get("normal_max")
        o_min = bm.get("optimal_min")
        o_max = bm.get("optimal_max")
        hr_min = bm.get("high_risk_min")
        hr_max = bm.get("high_risk_max")

        s = status
        if   "CRITICAL" in s: val_color, bg_accent = CRIT,   "rgba(229,62,62,0.05)"
        elif "HIGH"     in s: val_color, bg_accent = ORANGE, "rgba(249,123,90,0.05)"
        elif "LOW"      in s: val_color, bg_accent = PURPLE, "rgba(192,132,252,0.05)"
        else:                  val_color, bg_accent = BLUE,   "rgba(116,185,232,0.04)"

        try:
            fval = float(val)
            pill_html = render_pill_slider(fval, n_min, o_min, n_max, o_max, unit, status)
        except (ValueError, TypeError):
            pill_html = ""

        norm_str = _fmt_range(n_min, n_max)
        opt_target = _opt_target(o_min, o_max, n_min, n_max)

        if opt_target is not None:
            try:
                fval2 = float(val)
                diff = fval2 - opt_target
                to_opt = f"{'+' if diff > 0 else ''}{diff:.3g}"
                opt_label = f"Optimal: {opt_target:.4g}"
            except: to_opt = "—"; opt_label = ""
        else:
            to_opt = "—"; opt_label = ""

        hr_str = _fmt_range(hr_min, hr_max) if (hr_min is not None or hr_max is not None) else "—"

        prev = prev_values.get(test)
        prev_str = fmt(prev) if prev is not None else "—"

        st.markdown(f"""
        <div style="background:{SURFACE};border:1px solid {BORDER};border-left:4px solid {val_color};
             border-radius:14px;padding:1.2rem 1.5rem 0.75rem;margin-bottom:0.75rem;
             background:linear-gradient(135deg,{bg_accent} 0%,{SURFACE} 50%);
             overflow:hidden;">
          <div style="display:flex;gap:1.5rem;align-items:flex-start;flex-wrap:nowrap">
            <div style="min-width:140px;max-width:160px;flex-shrink:0">
              <div style="font-size:0.92rem;font-weight:700;color:{TEXT};line-height:1.3">⊕ {test}</div>
              <div style="font-size:0.72rem;color:{MUTED};margin-top:3px">{unit if unit else "—"}</div>
            </div>
            <div style="flex:1;display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;min-width:0">
              <div>
                <div style="font-size:0.62rem;color:{MUTED};letter-spacing:1px;text-transform:uppercase;margin-bottom:4px">Current</div>
                <div style="font-size:1.4rem;font-weight:700;color:{val_color};line-height:1">{fmt(val)}</div>
                <div style="height:1px;background:{BORDER};margin-top:6px"></div>
              </div>
              <div>
                <div style="font-size:0.62rem;color:{MUTED};letter-spacing:1px;text-transform:uppercase;margin-bottom:4px">Normal Range</div>
                <div style="font-size:0.88rem;font-weight:500;color:{TEXT};line-height:1.4">{norm_str}</div>
                <div style="height:1px;background:{BORDER};margin-top:6px"></div>
              </div>
              <div>
                <div style="font-size:0.62rem;color:{MUTED};letter-spacing:1px;text-transform:uppercase;margin-bottom:4px">To Optimal</div>
                <div style="font-size:0.88rem;font-weight:600;color:{TEXT};line-height:1.3">{to_opt}</div>
                <div style="font-size:0.68rem;color:{MUTED}">{opt_label}</div>
                <div style="height:1px;background:{BORDER};margin-top:6px"></div>
              </div>
              <div>
                <div style="font-size:0.62rem;color:{MUTED};letter-spacing:1px;text-transform:uppercase;margin-bottom:4px">Previous</div>
                <div style="font-size:0.88rem;color:{MUTED};line-height:1">{prev_str}</div>
                <div style="height:1px;background:{BORDER};margin-top:6px"></div>
              </div>
            </div>
          </div>
          <div style="margin-top:0.5rem;overflow:hidden">
            {pill_html}
          </div>
        </div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# RENDER: TREND CHARTS
# ─────────────────────────────────────────────

def render_trend_charts(history: pd.DataFrame, trends: pd.DataFrame, key_prefix: str = ""):
    test_names = sorted(trends["test_name"].tolist())
    if not test_names:
        return

    selected = st.multiselect(
        "Select biomarkers to chart",
        options=test_names,
        default=test_names[:min(4, len(test_names))],
        key=f"trend_chart_{key_prefix}",
        help="Choose tests to plot over time.",
    )
    if not selected:
        st.info("Select one or more biomarkers above to see charts.")
        return

    for test in selected:
        ts = get_test_timeseries(history, test)
        if ts.empty or len(ts) < 2:
            continue

        unit = clean_unit(ts["unit"].iloc[-1] if "unit" in ts.columns else "")
        bm   = bm_lookup(test)

        n_min  = bm.get("normal_min")
        n_max  = bm.get("normal_max")
        o_min  = bm.get("optimal_min")
        o_max  = bm.get("optimal_max")
        desc   = bm.get("short_description")
        interp = bm.get("interpretation_summary")

        lo = o_min if o_min is not None else n_min
        hi = o_max if o_max is not None else n_max

        y_vals = ts["value"].dropna()
        if y_vals.empty:
            continue
        candidates = list(y_vals) + [v for v in [lo, hi, n_min, n_max] if v is not None]
        axis_lo = min(candidates) * 0.82
        axis_hi = max(candidates) * 1.22

        point_colors = [_point_color(s) for s in ts["status"]]
        unit_label   = f" {unit}" if unit else ""

        fig = go.Figure()

        if lo is not None and hi is not None:
            fig.add_hrect(y0=lo, y1=hi,
                          fillcolor="rgba(78,205,196,0.06)",
                          line=dict(color=ACCENT, width=1, dash="dot"),
                          layer="below")
            fig.add_hrect(y0=hi, y1=axis_hi,
                          fillcolor="rgba(249,123,90,0.05)",
                          line_width=0, layer="below")
            fig.add_hrect(y0=axis_lo, y1=lo,
                          fillcolor="rgba(192,132,252,0.05)",
                          line_width=0, layer="below")
        elif hi is not None:
            fig.add_hrect(y0=hi, y1=axis_hi, fillcolor="rgba(249,123,90,0.05)", line_width=0, layer="below")
            fig.add_hrect(y0=axis_lo, y1=hi, fillcolor="rgba(78,205,196,0.06)", line_width=0, layer="below")
            fig.add_hline(y=hi, line=dict(color=ACCENT, width=1, dash="dot"), layer="below")
        elif lo is not None:
            fig.add_hrect(y0=axis_lo, y1=lo, fillcolor="rgba(192,132,252,0.05)", line_width=0, layer="below")
            fig.add_hrect(y0=lo, y1=axis_hi, fillcolor="rgba(78,205,196,0.06)", line_width=0, layer="below")
            fig.add_hline(y=lo, line=dict(color=ACCENT, width=1, dash="dot"), layer="below")

        for i in range(len(ts) - 1):
            seg_color = point_colors[i]
            fig.add_trace(go.Scatter(
                x=[ts["report_date"].iloc[i], ts["report_date"].iloc[i+1]],
                y=[ts["value"].iloc[i], ts["value"].iloc[i+1]],
                mode="lines",
                line=dict(color=seg_color, width=2.5, shape="spline"),
                showlegend=False,
                hoverinfo="skip",
            ))

        fig.add_trace(go.Scatter(
            x=ts["report_date"],
            y=ts["value"],
            mode="markers+text",
            marker=dict(
                color=point_colors,
                size=14,
                line=dict(color=SURFACE, width=3),
                symbol="circle",
            ),
            text=[f"{v:.4g}" for v in ts["value"]],
            textposition="top center",
            textfont=dict(color=TEXT, size=11, family="DM Sans"),
            hovertemplate=f"%{{x|%b %Y}}<br><b>%{{y:.4g}}</b>{unit_label}<extra></extra>",
            name=test,
        ))

        lo_s = f"{lo:.4g}" if lo is not None else "—"
        hi_s = f"{hi:.4g}" if hi is not None else "—"
        ann_text = (f"Target range: {lo_s} – {hi_s}{unit_label}"
                    if (lo is not None or hi is not None) else "")

        annotations = []
        if hi is not None:
            annotations.append(dict(
                xref="paper", yref="y", x=1.01, y=hi,
                text="Optimal", showarrow=False,
                font=dict(color=ACCENT, size=10, family="DM Sans"),
                xanchor="left",
            ))

        title_text = f"<b>{test}</b>"
        if unit:
            title_text += f"  <span style='font-size:11px;color:{MUTED}'>({unit})</span>"

        fig.update_layout(
            title=dict(text=title_text, font=dict(color=TEXT, size=15, family="DM Sans"), x=0),
            paper_bgcolor=SURFACE,
            plot_bgcolor=SURFACE,
            font=dict(color=MUTED, family="DM Sans"),
            xaxis=dict(
                showgrid=True, gridcolor=BORDER, gridwidth=1,
                tickformat="%b %Y",
                tickfont=dict(color=MUTED, size=11, family="DM Sans"),
                zeroline=False, showline=False,
            ),
            yaxis=dict(
                showgrid=True, gridcolor=BORDER, gridwidth=1,
                tickfont=dict(color=MUTED, size=11, family="DM Sans"),
                zeroline=False, showline=False,
                title=dict(text=unit, font=dict(color=MUTED, size=11)),
                range=[axis_lo, axis_hi],
            ),
            margin=dict(l=50, r=80, t=55, b=50),
            height=320, showlegend=False, hovermode="x unified",
            hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER,
                            font=dict(color=TEXT, family="DM Sans")),
            annotations=annotations,
        )

        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        if lo is not None or hi is not None:
            st.markdown(f"""
            <div class="range-legend" style="margin-top:0.25rem;margin-bottom:0.5rem">
              <span class="dot" style="background:{ACCENT}"></span>Optimal range
              <span class="dot" style="background:{ORANGE};margin-left:12px"></span>High
              <span class="dot" style="background:{PURPLE};margin-left:12px"></span>Low
              &nbsp;·&nbsp; <span style="font-size:0.68rem">{ann_text}</span>
            </div>""", unsafe_allow_html=True)

        has_d = desc   and pd.notna(desc)
        has_i = interp and pd.notna(interp)
        if has_d or has_i:
            html = '<div class="callout">'
            if has_d:
                html += f'<div class="callout-title">What it measures</div><p style="margin:0 0 6px">{desc}</p>'
            if has_i:
                html += f'<div class="callout-title" style="margin-top:6px">Interpretation</div><p style="margin:0">{interp}</p>'
            html += "</div>"
            st.markdown(html, unsafe_allow_html=True)

        st.markdown('<div style="height:1.5rem"></div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────
# RENDER: DUMBBELL CHANGE CHART
# ─────────────────────────────────────────────

def render_change_chart(trends: pd.DataFrame, key_prefix: str = ""):
    df = trends.dropna(subset=["first_value", "latest_value"]).copy()
    if df.empty:
        return
    df = df[df["n_reports"] >= 2].copy()
    if df.empty:
        return

    def row_color(r):
        s = str(r["latest_status"])
        pct = float(r["change_%"]) if pd.notna(r.get("change_%")) else 0
        if "CRITICAL" in s: return CRIT
        if "HIGH" in s:
            return ORANGE if pct > 0 else ACCENT
        if "LOW" in s:
            return PURPLE if pct < 0 else ACCENT
        return ACCENT

    df["_color"] = df.apply(row_color, axis=1)
    df["_pct"]   = df["change_%"].apply(lambda x: float(x) if pd.notna(x) else 0)
    df = df.sort_values("_pct", key=abs, ascending=False).head(20)

    fig = go.Figure()
    y_labels = df["test_name"].tolist()

    for i, (_, r) in enumerate(df.iterrows()):
        fv = float(r["first_value"])
        lv = float(r["latest_value"])
        fig.add_trace(go.Scatter(
            x=[fv, lv], y=[r["test_name"], r["test_name"]],
            mode="lines",
            line=dict(color=BORDER, width=2),
            showlegend=False, hoverinfo="skip",
        ))

    fig.add_trace(go.Scatter(
        x=df["first_value"].astype(float),
        y=df["test_name"],
        mode="markers",
        marker=dict(color=SURFACE, size=12, line=dict(color=MUTED, width=2.5)),
        name="Previous",
        hovertemplate="Previous: <b>%{x:.4g}</b><extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=df["latest_value"].astype(float),
        y=df["test_name"],
        mode="markers",
        marker=dict(color=df["_color"].tolist(), size=14,
                    line=dict(color=SURFACE, width=2.5)),
        name="Current",
        hovertemplate="Current: <b>%{x:.4g}</b><extra></extra>",
    ))

    for _, r in df.iterrows():
        pct = r["_pct"]
        lv  = float(r["latest_value"])
        arrow = "→"
        label = f"{arrow}{abs(pct):.1f}"
        lbl_color = r["_color"]
        fig.add_annotation(
            x=lv, y=r["test_name"],
            text=f'<span style="color:{lbl_color}">+{label}</span>' if pct > 0 else f'<span style="color:{lbl_color}">{label}</span>',
            showarrow=False, xanchor="left", xshift=18,
            font=dict(size=10, color=lbl_color, family="DM Mono"),
        )

    n_tests = len(df)
    chart_h = max(300, n_tests * 40 + 80)

    fig.update_layout(
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=MUTED, family="DM Sans"),
        xaxis=dict(showgrid=True, gridcolor=BORDER, zeroline=True,
                   zerolinecolor=BORDER, zerolinewidth=1,
                   tickfont=dict(color=MUTED, size=11)),
        yaxis=dict(showgrid=False, tickfont=dict(color=TEXT, size=11, family="DM Sans"),
                   categoryorder="array", categoryarray=y_labels[::-1]),
        margin=dict(l=180, r=80, t=30, b=40),
        height=chart_h, hovermode="y",
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
            font=dict(color=MUTED, size=11),
        ),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER, font=dict(color=TEXT, family="DM Sans")),
    )

    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


# ─────────────────────────────────────────────
# RENDER: TRENDS SECTION
# ─────────────────────────────────────────────

def render_trends_section(history: pd.DataFrame, trends: pd.DataFrame, key_prefix: str = ""):
    if trends.empty:
        st.info("Upload at least 2 reports for this patient to see trends.")
        return

    ab = trends[trends["latest_status"].str.contains("HIGH|LOW", na=False)]
    worsening = ab[
        (ab["latest_status"].str.contains("HIGH") & (ab["change_%"] > 0)) |
        (ab["latest_status"].str.contains("LOW")  & (ab["change_%"] < 0))
    ]
    improving = ab[
        (ab["latest_status"].str.contains("HIGH") & (ab["change_%"] < 0)) |
        (ab["latest_status"].str.contains("LOW")  & (ab["change_%"] > 0))
    ]

    if not worsening.empty:
        with st.expander(f"{len(worsening)} biomarker(s) worsening — abnormal & moving wrong way",
                         expanded=True):
            for _, r in worsening.iterrows():
                st.markdown(
                    f"{status_pill(r['latest_status'])} &nbsp;"
                    f"**{r['test_name']}** — {r['trend']} {abs(r['change_%']):.1f}%",
                    unsafe_allow_html=True,
                )

    if not improving.empty:
        with st.expander(f"{len(improving)} biomarker(s) improving — still abnormal but trending better"):
            for _, r in improving.iterrows():
                st.markdown(
                    f"{status_pill(r['latest_status'])} &nbsp;"
                    f"**{r['test_name']}** — {r['trend']} {abs(r['change_%']):.1f}% toward normal",
                    unsafe_allow_html=True,
                )

    st.markdown(f"""
    <div style="margin-top:1.5rem;margin-bottom:0.25rem">
      <div style="font-size:1.1rem;font-weight:700;color:{TEXT}">Biomarker Change</div>
      <div style="font-size:0.82rem;color:{MUTED};margin-top:2px">
        How each biomarker has changed since your previous report.
        Current values are shown in color, previous in grey.
      </div>
    </div>""", unsafe_allow_html=True)

    trends_with_2 = trends[trends["n_reports"] >= 2]
    if not trends_with_2.empty:
        render_change_chart(trends_with_2, key_prefix=key_prefix)
    else:
        st.info("Need at least 2 readings per biomarker to show changes.")

    st.markdown('<div class="section-label" style="margin-top:1.75rem">Trend Summary Table</div>',
                unsafe_allow_html=True)
    render_trends_table(trends)

    st.markdown('<div class="section-label" style="margin-top:1.75rem">Time Series Charts</div>',
                unsafe_allow_html=True)
    render_trend_charts(history, trends, key_prefix=key_prefix)

    st.download_button(
        "↓ Export Trends CSV",
        data=trends.to_csv(index=False).encode("utf-8"),
        file_name=f"{safe_name(history)}_trends.csv",
        mime="text/csv",
        key=f"{key_prefix}_dl_trends",
    )


# ─────────────────────────────────────────────
# API KEY
# ─────────────────────────────────────────────

@st.cache_data
def _get_api_key() -> str:
    k = ""
    if hasattr(st, "secrets"):
        k = st.secrets.get("ANTHROPIC_API_KEY", "")
    return k or os.environ.get("ANTHROPIC_API_KEY", "")


api_key     = _get_api_key()
llm_enabled = bool(api_key)


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────

with st.sidebar:
    st.markdown('<div class="section-label">Navigation</div>', unsafe_allow_html=True)
    pending      = load_pending_reviews()
    review_label = f"🔍 LLM Review  ({len(pending)})" if pending else "🔍 LLM Review"
    page = st.radio(
        "page",
        ["Upload Reports", "Patient Profiles", review_label, "About"],
        label_visibility="collapsed",
    )
    if page.startswith("🔍 LLM Review"):
        page = "LLM Review"

    st.markdown("---")
    st.markdown('<div class="section-label">Stored Patients</div>', unsafe_allow_html=True)
    for p in list_patients():
        icon = "♂" if str(p.get("gender", "")).upper() == "M" else "♀"
        st.markdown(
            f'<div style="font-size:0.82rem;color:{TEXT};margin-bottom:6px;line-height:1.4;'
            f'padding:6px 8px;border-radius:8px;background:{LIGHT}">'
            f'{icon} <strong>{p["patient_name"]}</strong>'
            f'<span style="color:{MUTED};margin-left:8px;font-size:0.72rem">'
            f'{p["n_reports"]} report(s)</span></div>',
            unsafe_allow_html=True,
        )

    if llm_enabled:
        st.markdown(f"""
        <div style="margin-top:1.5rem;padding:10px 12px;background:{LIGHT};
             border:1px solid {BORDER};border-left:3px solid {ACCENT};
             border-radius:10px;font-size:0.72rem;color:{MUTED}">
          🤖 Claude verification active
        </div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# PAGE HEADER
# ─────────────────────────────────────────────

st.markdown("""
<div class="bip-header">
  <h1>🧬 Biomarker Intelligence</h1>
  <span class="sub">Longitudinal Health Analytics</span>
</div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════
# PAGE: UPLOAD REPORTS
# ═══════════════════════════════════════════════

if page == "Upload Reports":
    st.markdown('<div class="section-label">Upload Lab Reports</div>', unsafe_allow_html=True)

    if llm_enabled:
        st.caption("🤖 Claude verification enabled — all values will be audited after extraction.")
    else:
        st.caption("⚪ LLM off — add ANTHROPIC_API_KEY to Streamlit secrets to enable Claude auditing.")

    uploaded_files = st.file_uploader(
        "Drop PDF lab reports here",
        type="pdf",
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if uploaded_files:
        with st.expander("⚙️  Date overrides — use if date was not auto-detected", expanded=False):
            st.caption(
                "Leave blank to use the date extracted from the PDF. "
                "Fill in only if Trends shows 'need at least 2 reports' "
                "after uploading multiple reports for the same patient."
            )
            date_overrides: dict = {}
            for uf in uploaded_files:
                v = st.text_input(
                    f"{uf.name}  (YYYY-MM-DD)", value="",
                    key=f"date_override_{uf.name}",
                    placeholder="e.g. 2024-11-28",
                )
                if v.strip():
                    date_overrides[uf.name] = v.strip()
    else:
        date_overrides = {}

    if uploaded_files and st.button("⟳  Process Reports", type="primary"):
        progress           = st.progress(0)
        results_by_patient: dict = {}

        for i, uf in enumerate(uploaded_files):
            tmp_path = _make_tmp(uf.read())

            if is_duplicate_file(tmp_path):
                st.warning(f"⏭️ **{uf.name}** — already processed, skipping.")
                progress.progress((i + 1) / len(uploaded_files))
                continue

            df, raw_text = process_pdf(tmp_path, verbose=False)

            if df.empty:
                st.warning(f"⚠️ **{uf.name}** — no data could be extracted.")
                progress.progress((i + 1) / len(uploaded_files))
                continue

            extracted_date = str(df["report_date"].iloc[0]) if not df.empty else ""
            override       = date_overrides.get(uf.name, "").strip()
            if override:
                df["report_date"] = override
                st.caption(f"📅 Date override applied for **{uf.name}**: {override}")
            elif not extracted_date or extracted_date in ("", "nan", "NaT", "None"):
                st.warning(
                    f"⚠️ **{uf.name}** — date not detected. "
                    "Expand **Date overrides** above, enter the date, then re-process."
                )

            ocr_used = bool(df.get("ocr_extracted", pd.Series([False])).iloc[0])
            pid      = df["patient_id"].iloc[0]
            name     = df["patient_name"].iloc[0]

            if llm_enabled:
                with st.spinner(f"🤖 Claude is auditing {uf.name}…"):
                    llm_result = verify_with_llm(raw_text, df, api_key=api_key)

                if llm_result.get("error"):
                    st.warning(f"⚠️ LLM check failed for **{uf.name}**: {llm_result['error']}")
                    save_report(df)
                else:
                    diff        = build_diff(df, llm_result)
                    meta_corr   = get_metadata_corrections(df, llm_result)
                    meta_issues = meta_corr.get("metadata_issues", [])

                    if meta_corr.get("date_correction") and not override:
                        df["report_date"] = meta_corr["date_correction"]
                        st.caption(
                            f"📅 Date found by Claude ({meta_corr.get('date_source','')}) → "
                            f"**{meta_corr['date_correction']}**"
                        )
                        meta_corr["date_correction"] = None

                    needs_review = diff[diff["needs_review"]] if not diff.empty else pd.DataFrame()
                    n_flags      = len(needs_review)
                    has_meta     = bool(
                        meta_corr.get("date_correction") or
                        meta_corr.get("name_correction") or meta_issues
                    )

                    if n_flags == 0 and not has_meta:
                        st.success(f"✓ **{uf.name}** — {len(df)} tests · {name} · 🤖 all confirmed")
                        df["llm_verified"] = True
                        save_report(df)
                    else:
                        save_report(df)
                        save_pending_review(pid, df["report_date"].iloc[0],
                                            diff, raw_text, meta_corr)
                        parts = []
                        if n_flags:     parts.append(f"{n_flags} flag(s)")
                        if meta_issues: parts.append(f"{len(meta_issues)} metadata issue(s)")
                        if has_meta:    parts.append("metadata correction(s)")
                        st.success(f"✓ **{uf.name}** — {len(df)} tests · {name}")
                        st.warning(f"🔍 **{', '.join(parts)} need review** — see LLM Review.")
            else:
                save_report(df)
                st.success(f"✓ **{uf.name}** — {len(df)} tests · {name}")

            if ocr_used:
                st.caption("📷 OCR was used — please verify hormone/thyroid values against the original PDF.")

            results_by_patient.setdefault(pid, []).append(df)
            progress.progress((i + 1) / len(uploaded_files))

        if results_by_patient:
            st.markdown("---")
            for pid in results_by_patient:
                history = load_history(pid)
                trends  = generate_trends(history)
                render_patient_card(history)
                tab1, tab2 = st.tabs(["Latest Results", "Trends"])
                with tab1:
                    snapshot = get_snapshot(history)
                    col_l, col_r = st.columns([1, 1.3])
                    with col_l:
                        render_summary_cards(snapshot)
                    with col_r:
                        render_radial_overview(snapshot, filter_status="all")
                    st.markdown(f'<hr style="border:none;border-top:1px solid {BORDER};margin:0.75rem 0">', unsafe_allow_html=True)
                    view_mode_ul = st.radio(
                        "View as",
                        ["Biomarker Cards", "Table"],
                        horizontal=True,
                        key=f"upload_view_{pid}",
                        label_visibility="collapsed",
                    )
                    if view_mode_ul == "Biomarker Cards":
                        render_biomarker_cards(snapshot, history=history)
                    else:
                        render_results_table(snapshot)
                    st.download_button(
                        "↓ Export CSV",
                        data=snapshot.to_csv(index=False).encode("utf-8"),
                        file_name=f"{safe_name(history)}_latest.csv",
                        mime="text/csv",
                        key=f"ul_snap_{pid}",
                    )
                with tab2:
                    render_trends_section(history, trends, key_prefix=f"ul_{pid}")
                st.markdown("---")

    elif not uploaded_files:
        st.markdown(f"""
        <div style="text-align:center;padding:4rem 2rem">
          <div style="font-size:3rem;margin-bottom:1rem">📄</div>
          <div style="font-size:1.05rem;font-weight:600;color:{TEXT};margin-bottom:0.5rem">
            Drop PDF lab reports to begin</div>
          <div style="font-size:0.82rem;color:{MUTED}">
            Supports Hitech, Kauvery, Metropolis and similar Indian labs.</div>
        </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════
# PAGE: PATIENT PROFILES
# ═══════════════════════════════════════════════

elif page == "Patient Profiles":
    st.markdown('<div class="section-label">Stored Patient Profiles</div>', unsafe_allow_html=True)
    patients = list_patients()

    if not patients:
        st.info("No patient profiles yet — upload some lab reports first.")
    else:
        patient_options = {
            f"{p['patient_name']}  ({p['n_reports']} report(s))": p["patient_id"]
            for p in patients
        }
        selected_label = st.selectbox(
            "Select Patient", list(patient_options.keys()),
            label_visibility="collapsed",
        )
        selected_pid = patient_options[selected_label]
        history      = load_history(selected_pid)

        if history.empty:
            st.error("Could not load this patient's profile.")
        else:
            render_patient_card(history)
            report_dates = sorted(
                history["report_date"].dropna().dt.strftime("%Y-%m-%d").unique(),
                reverse=True,
            )

            with st.expander("Manage Patient Data", expanded=False):
                current_name = history["patient_name"].iloc[0]

                st.markdown('<div class="section-label">Rename</div>', unsafe_allow_html=True)
                cn1, cn2, _ = st.columns([3, 1, 3])
                with cn1:
                    new_name = st.text_input(
                        "Name", value=current_name, key="rename_input",
                        label_visibility="collapsed"
                    )
                with cn2:
                    st.markdown("<div style='margin-top:0.35rem'></div>", unsafe_allow_html=True)
                    if st.button("💾 Save", key="rename_btn"):
                        if new_name.strip() and new_name.strip().upper() != current_name:
                            rename_patient(selected_pid, new_name)
                            st.success(f"Renamed to **{new_name.strip().upper()}**.")
                            st.rerun()
                        else:
                            st.info("No change.")

                other_patients = [(p["patient_id"], p["patient_name"])
                                  for p in patients if p["patient_id"] != selected_pid]
                if other_patients:
                    st.markdown("---")
                    st.markdown('<div class="section-label">Merge with another profile</div>',
                                unsafe_allow_html=True)
                    merge_options = {f"{p[1]}  ({p[0]})": p[0] for p in other_patients}
                    cm1, cm2, _ = st.columns([3, 1, 3])
                    with cm1:
                        ml = st.selectbox("Merge INTO →", list(merge_options.keys()),
                                          key="merge_target_select",
                                          label_visibility="collapsed")
                    with cm2:
                        st.markdown("<div style='margin-top:0.35rem'></div>", unsafe_allow_html=True)
                        if st.button("🔀 Merge", key="merge_btn"):
                            if merge_into_patient(selected_pid, merge_options[ml]):
                                st.success("Profiles merged.")
                                st.rerun()
                            else:
                                st.error("Merge failed.")

                st.markdown("---")
                st.markdown('<div class="section-label">Delete a report</div>', unsafe_allow_html=True)
                cd1, cd2, _ = st.columns([2, 1, 4])
                with cd1:
                    del_date = st.selectbox("Report", options=report_dates,
                                            key="del_date_select",
                                            label_visibility="collapsed")
                with cd2:
                    st.markdown("<div style='margin-top:0.35rem'></div>", unsafe_allow_html=True)
                    if st.button("🗑 Delete", key="del_report_btn"):
                        if delete_report_by_date(selected_pid, del_date):
                            st.success(f"Deleted {del_date}.")
                            st.rerun()
                        else:
                            st.error("Could not delete.")

                st.markdown("---")
                st.markdown(
                    f'<div class="section-label" style="color:{RED}">Danger zone</div>',
                    unsafe_allow_html=True,
                )
                st.warning(f"This will permanently erase all data for **{current_name}**.")
                if st.button("⛔ Delete Patient", key="del_patient_btn"):
                    delete_patient(selected_pid)
                    st.success("Deleted.")
                    st.rerun()

            trends = generate_trends(history)
            tab1, tab2, tab3 = st.tabs(["Latest Results", "Trends", "Full History"])

            with tab1:
                snapshot = get_snapshot(history)

                total    = len(snapshot)
                critical = snapshot["status"].str.contains("CRITICAL", na=False).sum()
                abnormal = snapshot["status"].str.contains("HIGH|LOW", na=False).sum()
                normal   = total - abnormal
                oor      = abnormal - critical
                pct_ok   = int(normal / total * 100) if total else 0
                bar_col  = ACCENT if pct_ok >= 80 else (AMBER if pct_ok >= 60 else ORANGE)

                filter_key = f"radial_filter_{selected_pid}"
                if filter_key not in st.session_state:
                    st.session_state[filter_key] = "all"
                active_filter = st.session_state[filter_key]

                col_left, col_right = st.columns([1, 1.3])

                with col_left:
                    cards = [
                        ("all",      total,    TEXT,   "Total Tests"),
                        ("normal",   normal,   ACCENT, "Within Range"),
                        ("oor",      oor,      ORANGE, "Out of Range"),
                        ("critical", critical, CRIT,   "Critical"),
                    ]
                    c1, c2, c3, c4 = st.columns(4)
                    for col_btn, (fkey, num, color, label) in zip([c1,c2,c3,c4], cards):
                        is_active = active_filter == fkey
                        bg = f"rgba({','.join(str(int(color[i:i+2],16)) for i in (1,3,5))},0.08)" if is_active and color != TEXT else (LIGHT if is_active else SURFACE)
                        border = f"2px solid {color}" if is_active else f"1px solid {BORDER}"
                        with col_btn:
                            st.markdown(f"""
                            <div style="background:{bg};border:{border};border-radius:14px;
                                 padding:1rem 0.5rem;text-align:center;cursor:pointer;
                                 box-shadow:{'0 4px 14px rgba(0,0,0,0.10)' if is_active else '0 1px 4px rgba(0,0,0,0.04)'};
                                 transition:all 0.15s;margin-bottom:2px">
                              <div style="font-size:2rem;font-weight:700;color:{color};
                                   line-height:1;letter-spacing:-1px">{num}</div>
                              <div style="font-size:0.68rem;color:{MUTED};margin-top:5px;
                                   font-weight:{'600' if is_active else '400'}">{label}</div>
                            </div>""", unsafe_allow_html=True)
                            if st.button("Filter", key=f"flt_{selected_pid}_{fkey}",
                                         width="stretch",
                                         help=f"Show {label} in radial chart"):
                                st.session_state[filter_key] = fkey
                                st.rerun()

                    st.markdown(f"""
                    <div style="margin-top:0.75rem;margin-bottom:0.5rem">
                      <div style="display:flex;justify-content:space-between;margin-bottom:5px">
                        <span style="font-size:0.75rem;color:{MUTED}">Within-Range Score</span>
                        <span style="font-size:0.8rem;font-weight:700;color:{bar_col}">{pct_ok}%</span>
                      </div>
                      <div style="background:{BORDER};border-radius:8px;height:6px">
                        <div style="width:{pct_ok}%;height:100%;background:{bar_col};
                               border-radius:8px;transition:width 0.6s ease"></div>
                      </div>
                    </div>""", unsafe_allow_html=True)

                with col_right:
                    filter_labels = {"all": "All Biomarkers", "normal": "Within Range",
                                     "oor": "Out of Range", "critical": "Critical Only"}
                    st.markdown(
                        f'<div style="font-size:0.85rem;font-weight:600;color:{TEXT};margin-bottom:1px">'
                        f'Biomarker Map · <span style="color:{MUTED};font-weight:400;font-size:0.8rem">'
                        f'{filter_labels.get(active_filter,"All")}</span></div>'
                        f'<div style="font-size:0.72rem;color:{MUTED};margin-bottom:0.4rem;line-height:1.5">'
                        f'Each dot is one biomarker. Dots in the <b style="color:{ACCENT}">teal inner ring</b> are optimal. '
                        f'Dots in the <b style="color:{ORANGE}">outer ring</b> need attention. '
                        f'Click a card on the left to highlight a group.</div>',
                        unsafe_allow_html=True
                    )
                    render_radial_overview(snapshot, filter_status=active_filter)

                st.markdown(f'<hr style="border:none;border-top:1px solid {BORDER};margin:0.75rem 0">', unsafe_allow_html=True)

                view_mode = st.radio(
                    "View as",
                    ["Biomarker Cards", "Table"],
                    horizontal=True,
                    key=f"view_mode_{selected_pid}",
                    label_visibility="collapsed",
                )
                if view_mode == "Biomarker Cards":
                    render_biomarker_cards(snapshot, history=history)
                else:
                    render_results_table(snapshot)

                # ── FIX: Only ONE download button here (duplicate was removed) ──
                st.download_button(
                    "↓ Export Latest CSV",
                    data=snapshot.to_csv(index=False).encode("utf-8"),
                    file_name=f"{safe_name(history)}_latest.csv",
                    mime="text/csv",
                    key=f"pp_snap_{selected_pid}",
                )

            with tab2:
                render_trends_section(history, trends, key_prefix=f"pp_{selected_pid}")

            with tab3:
                st.markdown('<div class="section-label">All Records</div>', unsafe_allow_html=True)
                show_cols = ["report_date", "test_name", "value", "unit", "status", "source_file"]
                avail     = [c for c in show_cols if c in history.columns]
                disp      = history[avail].copy()
                disp["unit"] = disp["unit"].apply(clean_unit)
                st.dataframe(
                    disp.sort_values(["report_date", "test_name"], ascending=[False, True]),
                    width="stretch",
                    hide_index=True,
                )
                st.download_button(
                    "↓ Full History CSV",
                    data=history.to_csv(index=False).encode("utf-8"),
                    file_name=f"{safe_name(history)}_full_history.csv",
                    mime="text/csv",
                    key=f"pp_hist_{selected_pid}",
                )

                st.markdown("---")
                st.markdown(
                    '<div class="section-label">✏️ Manually Correct a Result</div>',
                    unsafe_allow_html=True,
                )
                st.caption(
                    "Use when both regex and Claude got a value wrong. "
                    "Status (HIGH/LOW/Normal) will be re-computed automatically."
                )

                ec1, ec2 = st.columns(2)
                with ec1:
                    edit_date = st.selectbox("Report date", options=report_dates,
                                             key=f"edit_date_{selected_pid}")
                with ec2:
                    date_tests = sorted(
                        history[history["report_date"].dt.strftime("%Y-%m-%d") == edit_date
                               ]["test_name"].unique().tolist()
                    )
                    edit_test = st.selectbox("Test to correct", options=date_tests,
                                             key=f"edit_test_{selected_pid}")

                cur_row  = history[
                    (history["report_date"].dt.strftime("%Y-%m-%d") == edit_date) &
                    (history["test_name"] == edit_test)
                ]
                cur_val  = float(cur_row["value"].iloc[0]) if not cur_row.empty else 0.0
                cur_unit = clean_unit(cur_row["unit"].iloc[0] if not cur_row.empty else "")

                vc, uc, bc = st.columns([2, 2, 1])
                with vc:
                    new_val = st.number_input(
                        f"Value  (stored: {cur_val:.4g})",
                        value=cur_val, format="%.4f",
                        key=f"edit_val_{selected_pid}_{edit_date}_{edit_test}",
                    )
                with uc:
                    new_unit = st.text_input(
                        f"Unit  (stored: {cur_unit or '—'})",
                        value=cur_unit,
                        key=f"edit_unit_{selected_pid}_{edit_date}_{edit_test}",
                    )
                with bc:
                    st.markdown("<div style='margin-top:1.75rem'></div>", unsafe_allow_html=True)
                    if st.button("💾 Save", key=f"edit_save_{selected_pid}_{edit_date}_{edit_test}"):
                        if abs(new_val - cur_val) > 1e-6 or new_unit.strip() != cur_unit.strip():
                            ok = patch_record(selected_pid, edit_date, edit_test,
                                              new_value=new_val, new_unit=new_unit.strip())
                            if ok:
                                st.success(f"✓ **{edit_test}** → {new_val:.4g} {new_unit.strip()}")
                                st.rerun()
                            else:
                                st.error("Record not found.")
                        else:
                            st.info("No change detected.")


# ═══════════════════════════════════════════════
# PAGE: LLM REVIEW
# ═══════════════════════════════════════════════

elif page == "LLM Review":
    st.markdown('<div class="section-label">LLM Verification Review</div>', unsafe_allow_html=True)
    st.markdown(
        "Claude audited each report for **missing fields**, **wrong/missing units**, "
        "**date detection**, **out-of-range values**, and **missed tests**. "
        "Every flag requires your approval before anything changes."
    )

    st.markdown(f"""
    <div style="display:flex;gap:1.25rem;flex-wrap:wrap;margin:0.75rem 0 1.25rem;
         padding:0.75rem 1.25rem;background:{SURFACE};border:1px solid {BORDER};border-radius:12px;
         font-size:0.75rem;color:{MUTED}">
      <span>🆕 <b style="color:{TEXT}">MISSED</b> — in PDF but skipped by regex</span>
      <span>⚠️ <b style="color:{TEXT}">CORRECTED</b> — value/unit differs</span>
      <span>🔴 <b style="color:{CRIT}">CRITICAL</b> — danger zone</span>
      <span>📊 <b style="color:{ORANGE}">HIGH</b> / <b style="color:{PURPLE}">LOW</b> — out of range</span>
      <span>📋 <b style="color:{TEXT}">METADATA</b> — date/name/unit issue</span>
      <span>❓ <b style="color:{TEXT}">LOW CONFIDENCE</b> — Claude unsure</span>
    </div>""", unsafe_allow_html=True)

    pending = load_pending_reviews()
    if not pending:
        st.success("✓ No pending reviews — all reports verified.")
    else:
        for review in pending:
            pid         = review["patient_id"]
            report_date = review["report_date"]
            diff_rows   = review.get("diff", [])
            meta_corr   = review.get("meta_corrections", {})

            history      = load_history(pid)
            patient_name = history["patient_name"].iloc[0] if not history.empty else pid

            diff    = pd.DataFrame(diff_rows) if diff_rows else pd.DataFrame()
            flagged = diff[diff["needs_review"] == True] if not diff.empty else pd.DataFrame()

            meta_issues     = meta_corr.get("metadata_issues", [])
            date_correction = meta_corr.get("date_correction")
            name_correction = meta_corr.get("name_correction")
            has_meta        = bool(meta_issues or date_correction or name_correction)
            total_items     = (len(flagged) +
                               (1 if date_correction else 0) +
                               (1 if name_correction else 0) +
                               len(meta_issues))

            if total_items == 0 and flagged.empty:
                delete_pending_review(pid, report_date)
                continue

            with st.expander(
                f"📋  {patient_name}  ·  {report_date}  ·  {total_items} item(s)",
                expanded=True,
            ):
                accepted_tests: list = []
                rejected_tests: list = []
                apply_date = reject_date = apply_name = reject_name = False

                if has_meta:
                    st.markdown('<div class="section-label">Metadata Issues</div>',
                                unsafe_allow_html=True)
                    for issue in meta_issues:
                        st.warning(f"📋 {issue}")

                    if date_correction:
                        ci, ca, cr = st.columns([5, 1, 1])
                        with ci:
                            src = meta_corr.get("date_source", "report text")
                            st.markdown("📋 **Date Correction**")
                            st.caption(
                                f"Claude read **{date_correction}** from '{src}'.  "
                                f"Stored: **{report_date or '(empty)'}**"
                            )
                        with ca:
                            if st.button("✓", key=f"acc_date_{pid}_{report_date}", type="primary"):
                                apply_date = True
                        with cr:
                            if st.button("✗", key=f"rej_date_{pid}_{report_date}"):
                                reject_date = True

                    if name_correction:
                        ci, ca, cr = st.columns([5, 1, 1])
                        with ci:
                            regex_name = history["patient_name"].iloc[0] if not history.empty else "?"
                            st.markdown("📋 **Name Correction**")
                            st.caption(f"Stored: **{regex_name}** → Claude: **{name_correction}**")
                        with ca:
                            if st.button("✓", key=f"acc_name_{pid}_{report_date}", type="primary"):
                                apply_name = True
                        with cr:
                            if st.button("✗", key=f"rej_name_{pid}_{report_date}"):
                                reject_name = True

                if not flagged.empty:
                    st.markdown(
                        '<div class="section-label" style="margin-top:1.25rem">'
                        'Value &amp; Range Checks</div>',
                        unsafe_allow_html=True,
                    )
                    for _, row in flagged.iterrows():
                        test   = row["test_name"]
                        status = row["status"]
                        conf   = row.get("confidence", "high")
                        note   = row.get("note", "")
                        r_val  = row["regex_value"]
                        r_unit = clean_unit(row.get("regex_unit", ""))
                        l_val  = row["llm_value"]
                        l_unit = clean_unit(row.get("llm_unit", ""))
                        rflag  = row.get("range_flag", "")
                        rnote  = row.get("range_note", "")
                        unote  = row.get("unit_note", "")

                        if   status == "missed_by_regex":
                            badge = "🆕 **MISSED**"
                            desc  = f"Regex skipped this. Claude found: **{l_val} {l_unit}**"
                        elif status == "corrected":
                            badge = "⚠️ **CORRECTED**"
                            desc  = f"Regex: **{r_val} {r_unit}** → Claude: **{l_val} {l_unit}**"
                            if unote: desc += f"  _(unit: {unote})_"
                        else:
                            badge = "❓ **LOW CONFIDENCE**"
                            desc  = f"Regex: **{r_val} {r_unit}** — Claude unsure"

                        rflag_html  = ""
                        rflag_color = TEXT
                        if   rflag == "CRITICAL_HIGH": rflag_html, rflag_color = "🔴 CRITICAL HIGH", CRIT
                        elif rflag == "CRITICAL_LOW":  rflag_html, rflag_color = "🔴 CRITICAL LOW",  CRIT
                        elif rflag == "HIGH":           rflag_html, rflag_color = "📊 HIGH",           ORANGE
                        elif rflag == "LOW":            rflag_html, rflag_color = "📊 LOW",            PURPLE

                        ci, ca, cr = st.columns([5, 1, 1])
                        with ci:
                            hdr = badge
                            if rflag_html:
                                hdr += f' &nbsp;<span style="color:{rflag_color};font-size:0.8rem">{rflag_html}</span>'
                            st.markdown(f"{hdr} &nbsp; **{test}**", unsafe_allow_html=True)
                            parts = [desc]
                            if rnote: parts.append(f"Range: _{rnote}_")
                            if note:  parts.append(f"Note: _{note}_")
                            if conf == "low": parts.append("⚠️ Low confidence")
                            st.caption("  \n".join(parts))

                        wk = f"review_{pid}_{report_date}_{test}"
                        with ca:
                            if st.button("✓", key=f"acc_{wk}", type="primary"):
                                accepted_tests.append(test)
                        with cr:
                            if st.button("✗", key=f"rej_{wk}"):
                                rejected_tests.append(test)

                    st.markdown("---")
                    ca2, cr2, _ = st.columns([1.5, 1.5, 5])
                    with ca2:
                        if st.button("✓ Accept All", key=f"acc_all_{pid}_{report_date}"):
                            accepted_tests = flagged["test_name"].tolist()
                    with cr2:
                        if st.button("✗ Reject All", key=f"rej_all_{pid}_{report_date}"):
                            rejected_tests = flagged["test_name"].tolist()

                any_decision = (accepted_tests or rejected_tests or
                                apply_date or reject_date or apply_name or reject_name)

                if any_decision:
                    cur_hist  = load_history(pid)
                    report_df = cur_hist[
                        cur_hist["report_date"].dt.strftime("%Y-%m-%d") == report_date
                    ].copy()

                    eff_meta: dict = {}
                    if apply_date and date_correction:
                        eff_meta["date_correction"] = date_correction
                    if apply_name and name_correction:
                        eff_meta["name_correction"] = name_correction

                    if not report_df.empty and (accepted_tests or eff_meta):
                        corrected = apply_corrections(report_df, diff, accepted_tests,
                                                      meta_corrections=eff_meta or None)
                        other = cur_hist[
                            cur_hist["report_date"].dt.strftime("%Y-%m-%d") != report_date
                        ]
                        full = pd.concat([other, corrected], ignore_index=True)
                        (STORE_DIR / f"{pid}.csv").write_text(full.to_csv(index=False))

                        msgs = []
                        if accepted_tests:                    msgs.append(f"{len(accepted_tests)} correction(s)")
                        if eff_meta.get("date_correction"):   msgs.append(f"date → {eff_meta['date_correction']}")
                        if eff_meta.get("name_correction"):   msgs.append(f"name → {eff_meta['name_correction']}")
                        st.success(f"✓ Applied: {', '.join(msgs)}")

                    if rejected_tests: st.info(f"Rejected {len(rejected_tests)} suggestion(s).")
                    if reject_date:    st.info("Date correction rejected.")
                    if reject_name:    st.info("Name correction rejected.")

                    remaining = [t for t in flagged["test_name"]
                                 if t not in accepted_tests and t not in rejected_tests]
                    date_done = apply_date  or reject_date  or not date_correction
                    name_done = apply_name  or reject_name  or not name_correction
                    if not remaining and date_done and name_done:
                        delete_pending_review(pid, report_date)
                        st.rerun()


# ═══════════════════════════════════════════════
# PAGE: ABOUT
# ═══════════════════════════════════════════════

elif page == "About":
    st.markdown(f"""
    <div style="max-width:640px">
      <div class="section-label">About</div>
      <p style="color:{TEXT};line-height:1.85;font-size:0.88rem">
        The <strong>Longitudinal Biomarker Intelligence Platform</strong>
        extracts structured data from PDF lab reports, flags out-of-range results,
        and tracks health trends across multiple reports over time.
      </p>
      <div class="section-label" style="margin-top:2rem">How it works</div>
      <p style="color:{MUTED};line-height:1.85;font-size:0.85rem">
        1. Upload PDF lab reports — patient identity is detected automatically.<br>
        2. Biomarkers are matched against a dictionary with 75+ canonical names and
           sex-specific normal ranges.<br>
        3. Values outside the reference range are flagged HIGH / LOW / CRITICAL.<br>
        4. Across multiple reports, trend direction, change %, and charts are generated.<br>
        5. Duplicate uploads are detected by file hash and skipped.<br>
        6. Claude audits every extraction — catching wrong values, missing units,
           missed tests, and date errors.
      </p>
      <div class="section-label" style="margin-top:2rem">Chart colour guide</div>
      <p style="color:{MUTED};line-height:1.85;font-size:0.85rem">
        <span style="color:{ACCENT}">■</span> Teal (Optimized) — value within optimal range<br>
        <span style="color:{BLUE}">■</span> Blue (Balanced) — within normal range<br>
        <span style="color:{PURPLE}">■</span> Lavender (Moderate/Low) — below lower limit<br>
        <span style="color:{ORANGE}">■</span> Coral (Out of Range/High) — above upper limit<br>
        <span style="color:{CRIT}">■</span> Red — critical danger zone
      </p>
      <div class="section-label" style="margin-top:2rem">Privacy</div>
      <p style="color:{MUTED};line-height:1.85;font-size:0.85rem">
        All processing is local to the server. Patient profiles are stored as CSV files in
        <code style="color:{ACCENT}">data/patient_profiles/</code>.
        Do not commit that directory to a public repository.
      </p>
    </div>""", unsafe_allow_html=True)