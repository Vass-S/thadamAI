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
# PALETTE  — edit once, reflected everywhere
# ─────────────────────────────────────────────
BG       = "#090c12"
SURFACE  = "#0f1520"
SURFACE2 = "#151e2e"
BORDER   = "#1e2d42"
ACCENT   = "#22d3c8"
GREEN    = "#22c55e"
AMBER    = "#f59e0b"
RED      = "#ef4444"
CRIT     = "#ff1a1a"
TEXT     = "#e2e8f0"
MUTED    = "#64748b"
GREEN_Z  = "rgba(34,197,94,0.11)"
AMBER_Z  = "rgba(245,158,11,0.11)"
RED_Z    = "rgba(239,68,68,0.11)"

# ─────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root{{--bg:{BG};--surface:{SURFACE};--surface2:{SURFACE2};--border:{BORDER};--accent:{ACCENT};--green:{GREEN};--amber:{AMBER};--red:{RED};--crit:{CRIT};--text:{TEXT};--muted:{MUTED};}}
html,body,[class*="css"]{{background-color:var(--bg)!important;color:var(--text)!important;font-family:'Inter',sans-serif!important;}}
section[data-testid="stSidebar"]{{background-color:var(--surface)!important;border-right:1px solid var(--border)!important;}}
section[data-testid="stSidebar"] *{{color:var(--text)!important;}}
.bip-header{{display:flex;align-items:center;gap:14px;padding-bottom:1.25rem;margin-bottom:1.75rem;border-bottom:1px solid var(--border);}}
.bip-header h1{{font-size:1.65rem!important;font-weight:700!important;color:#fff!important;margin:0!important;letter-spacing:-0.4px;}}
.bip-header .sub{{font-family:'JetBrains Mono',monospace;font-size:0.62rem;letter-spacing:3px;text-transform:uppercase;color:var(--accent);background:rgba(34,211,200,0.08);border:1px solid rgba(34,211,200,0.2);padding:3px 10px;border-radius:20px;}}
.section-label{{font-family:'JetBrains Mono',monospace;font-size:0.58rem;letter-spacing:3px;text-transform:uppercase;color:var(--muted);margin:1.5rem 0 0.6rem;}}
.patient-card{{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--accent);padding:1.25rem 1.5rem;border-radius:8px;margin-bottom:1.5rem;display:grid;grid-template-columns:repeat(4,1fr);gap:1.25rem;}}
.patient-card .field label{{font-family:'JetBrains Mono',monospace;font-size:0.56rem;letter-spacing:2.5px;text-transform:uppercase;color:var(--muted);display:block;margin-bottom:5px;}}
.patient-card .field value{{font-size:1.05rem;font-weight:600;color:#fff;}}
.summary-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:0.75rem;margin-bottom:1.25rem;}}
.summary-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem 1.1rem;text-align:center;transition:transform 0.15s,border-color 0.15s;}}
.summary-card:hover{{border-color:var(--accent);transform:translateY(-1px);}}
.summary-card .num{{font-size:2.2rem;font-weight:700;line-height:1;font-variant-numeric:tabular-nums;}}
.summary-card .lbl{{font-family:'JetBrains Mono',monospace;font-size:0.58rem;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-top:5px;}}
.callout{{background:var(--surface2);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:0 6px 6px 0;padding:0.7rem 1rem;margin-top:0.4rem;font-size:0.82rem;line-height:1.7;color:var(--muted);}}
.callout b{{color:var(--text);}}
.callout-title{{font-family:'JetBrains Mono',monospace;font-size:0.55rem;letter-spacing:2px;text-transform:uppercase;color:var(--accent);margin-bottom:4px;}}
.range-legend{{display:inline-flex;align-items:center;gap:6px;font-size:0.7rem;color:var(--muted);margin-bottom:0.4rem;}}
.dot{{width:9px;height:9px;border-radius:50%;display:inline-block;}}
.stButton>button{{background:transparent!important;border:1px solid var(--accent)!important;color:var(--accent)!important;font-family:'JetBrains Mono',monospace!important;font-size:0.7rem!important;letter-spacing:1.5px!important;text-transform:uppercase!important;border-radius:5px!important;padding:0.4rem 1rem!important;transition:all 0.15s ease!important;}}
.stButton>button:hover{{background:var(--accent)!important;color:#000!important;}}
.stTabs [data-baseweb="tab-list"]{{border-bottom:1px solid var(--border)!important;gap:0;background:transparent!important;}}
.stTabs [data-baseweb="tab"]{{background:transparent!important;border-radius:0!important;color:var(--muted)!important;font-family:'JetBrains Mono',monospace!important;font-size:0.68rem!important;letter-spacing:1.5px!important;text-transform:uppercase!important;padding:0.6rem 1.4rem!important;border-bottom:2px solid transparent!important;transition:color 0.15s!important;}}
.stTabs [aria-selected="true"]{{color:var(--accent)!important;border-bottom:2px solid var(--accent)!important;}}
.stTabs [data-baseweb="tab"]:hover{{color:var(--text)!important;}}
.stFileUploader>div{{background:var(--surface)!important;border:1px dashed rgba(34,211,200,0.3)!important;border-radius:6px!important;}}
.stFileUploader>div:hover{{border-color:var(--accent)!important;}}
.stDataFrame{{border:1px solid var(--border)!important;border-radius:6px;}}
.stSelectbox>div>div,.stTextInput>div>div>input,.stNumberInput>div>div>input{{background:var(--surface)!important;border:1px solid var(--border)!important;color:var(--text)!important;border-radius:5px!important;}}
.stSelectbox>div>div:focus-within,.stTextInput>div>div:focus-within,.stNumberInput>div>div:focus-within{{border-color:var(--accent)!important;box-shadow:0 0 0 2px rgba(34,211,200,0.15)!important;}}
.streamlit-expanderHeader{{background:var(--surface)!important;border:1px solid var(--border)!important;border-radius:6px!important;font-size:0.85rem!important;}}
.stDownloadButton>button{{background:transparent!important;border:1px solid var(--border)!important;color:var(--muted)!important;font-family:'JetBrains Mono',monospace!important;font-size:0.66rem!important;border-radius:5px!important;}}
.stDownloadButton>button:hover{{border-color:var(--muted)!important;color:var(--text)!important;}}
.stProgress>div>div>div>div{{background:var(--accent)!important;}}
.stPlotlyChart{{border:1px solid var(--border);border-radius:6px;overflow:hidden;}}
/* Alert boxes */
div[data-testid="stAlert"]{{border-radius:6px!important;}}
div[data-testid="stNotification"]{{border-radius:6px!important;}}
[data-testid="stAlert"][data-baseweb="notification"]{{background:var(--surface2)!important;}}
/* Spinner */
div[data-testid="stSpinner"]>div{{border-top-color:var(--accent)!important;}}
/* Caption text */
.stCaptionContainer p{{color:var(--muted)!important;font-size:0.78rem!important;}}
/* Multiselect */
div[data-baseweb="tag"]{{background:rgba(34,211,200,0.12)!important;border:1px solid rgba(34,211,200,0.25)!important;}}
div[data-baseweb="tag"] span{{color:var(--accent)!important;}}
/* Help tooltip icon */
[data-testid="stWidgetLabel"] svg{{fill:var(--muted)!important;}}
#MainMenu,footer,.stDeployButton{{visibility:hidden;}}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# BIOMARKER DICTIONARY  (cached — loaded once)
# ─────────────────────────────────────────────

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


def bm_lookup(test_name: str) -> dict:
    """Return biomarker dict row as a plain dict, or {} if not found."""
    if biomarker_dictionary.empty or test_name not in biomarker_dictionary.index:
        return {}
    row = biomarker_dictionary.loc[test_name]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]
    return row.to_dict()


# ─────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────

def clean_unit(u) -> str:
    """Fix mangled µ character and strip NaN/None placeholders."""
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
    if "HIGH"     in s: return RED
    if "LOW"      in s: return AMBER
    return GREEN


def status_pill(status: str) -> str:
    s = str(status)
    if "CRITICAL" in s:
        return f'<span style="color:{CRIT};font-weight:700">{s}</span>'
    if "HIGH" in s:
        return f'<span style="color:{RED};font-weight:700">{s}</span>'
    if "LOW" in s:
        return f'<span style="color:{AMBER};font-weight:700">{s}</span>'
    return f'<span style="color:{GREEN}">{s or "Normal"}</span>'


# Temp file registry — cleaned up when the process exits
_tmp_files: list[str] = []

def _make_tmp(data: bytes, suffix: str = ".pdf") -> Path:
    """Write bytes to a named temp file, register for cleanup, return path."""
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
    """Latest result per test — used in multiple places."""
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
# RENDER: SUMMARY CARDS  (4-up + score bar)
# ─────────────────────────────────────────────

def render_summary_cards(snapshot: pd.DataFrame):
    total    = len(snapshot)
    critical = snapshot["status"].str.contains("CRITICAL", na=False).sum()
    abnormal = snapshot["status"].str.contains("HIGH|LOW", na=False).sum()
    normal   = total - abnormal
    oor      = abnormal - critical   # out-of-range but not critical
    pct_ok   = int(normal / total * 100) if total else 0
    bar_col  = GREEN if pct_ok >= 80 else (AMBER if pct_ok >= 60 else RED)

    st.markdown(f"""
    <div class="summary-grid">
      <div class="summary-card">
        <div class="num" style="color:#fff">{total}</div>
        <div class="lbl">Tests</div>
      </div>
      <div class="summary-card">
        <div class="num" style="color:{GREEN}">{normal}</div>
        <div class="lbl">Within Range</div>
      </div>
      <div class="summary-card">
        <div class="num" style="color:{AMBER}">{oor}</div>
        <div class="lbl">Out of Range</div>
      </div>
      <div class="summary-card">
        <div class="num" style="color:{CRIT}">{critical}</div>
        <div class="lbl">Critical</div>
      </div>
    </div>
    <div style="margin-bottom:1.25rem">
      <div style="display:flex;justify-content:space-between;margin-bottom:4px">
        <span style="font-family:'JetBrains Mono',monospace;font-size:0.57rem;
               letter-spacing:2px;text-transform:uppercase;color:{MUTED}">
          Within-Range Score</span>
        <span style="font-family:'JetBrains Mono',monospace;font-size:0.75rem;
               font-weight:600;color:{bar_col}">{pct_ok}%</span>
      </div>
      <div style="background:{BORDER};border-radius:4px;height:5px">
        <div style="width:{pct_ok}%;height:100%;background:{bar_col};
               border-radius:4px;transition:width 0.4s"></div>
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

    # Emoji prefix on status makes it scannable without colour (accessibility)
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
        use_container_width=True,
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

    # Trend arrow with direction context
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
        use_container_width=True,
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
# RENDER: TREND CHARTS  (coloured reference zones)
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

        # Prefer optimal range for green band; fall back to normal
        lo = o_min if o_min is not None else n_min
        hi = o_max if o_max is not None else n_max

        # Y-axis range with padding
        y_vals = ts["value"].dropna()
        if y_vals.empty:
            continue
        candidates = list(y_vals) + [v for v in [lo, hi, n_min, n_max] if v is not None]
        axis_lo = min(candidates) * 0.85
        axis_hi = max(candidates) * 1.20

        point_colors = [_point_color(s) for s in ts["status"]]
        unit_label   = f" {unit}" if unit else ""

        fig = go.Figure()

        # ── Reference zone bands ────────────────────────────────────────
        if lo is not None and hi is not None:
            # Red above upper limit
            fig.add_hrect(y0=hi, y1=axis_hi, fillcolor=RED_Z,   line_width=0, layer="below")
            # Amber below lower limit
            fig.add_hrect(y0=axis_lo, y1=lo, fillcolor=AMBER_Z, line_width=0, layer="below")
            # Green = normal band
            fig.add_hrect(y0=lo, y1=hi,      fillcolor=GREEN_Z, line_width=0, layer="below")
            # Dashed boundary lines
            fig.add_hline(y=hi, line=dict(color=RED,   width=1, dash="dot"), layer="below")
            fig.add_hline(y=lo, line=dict(color=AMBER, width=1, dash="dot"), layer="below")
        elif hi is not None:
            fig.add_hrect(y0=hi,     y1=axis_hi, fillcolor=RED_Z,   line_width=0, layer="below")
            fig.add_hrect(y0=axis_lo, y1=hi,     fillcolor=GREEN_Z, line_width=0, layer="below")
            fig.add_hline(y=hi, line=dict(color=RED, width=1, dash="dot"), layer="below")
        elif lo is not None:
            fig.add_hrect(y0=axis_lo, y1=lo, fillcolor=AMBER_Z, line_width=0, layer="below")
            fig.add_hrect(y0=lo, y1=axis_hi,  fillcolor=GREEN_Z, line_width=0, layer="below")
            fig.add_hline(y=lo, line=dict(color=AMBER, width=1, dash="dot"), layer="below")

        # ── Data trace ──────────────────────────────────────────────────
        fig.add_trace(go.Scatter(
            x=ts["report_date"],
            y=ts["value"],
            mode="lines+markers+text",
            line=dict(color=ACCENT, width=2.5),
            marker=dict(color=point_colors, size=11, line=dict(color=BG, width=2)),
            text=[f"{v:.4g}" for v in ts["value"]],
            textposition="top center",
            textfont=dict(color=TEXT, size=11, family="JetBrains Mono"),
            hovertemplate=f"%{{x|%d %b %Y}}<br><b>%{{y:.4g}}</b>{unit_label}<extra></extra>",
            name=test,
        ))

        # ── Annotation: normal range ─────────────────────────────────────
        lo_s = f"{lo:.4g}" if lo is not None else "—"
        hi_s = f"{hi:.4g}" if hi is not None else "—"
        ann_text = (f"Normal: {lo_s} – {hi_s}{unit_label}"
                    if (lo is not None or hi is not None) else "")

        title_text = f"<b>{test}</b>"
        if unit:
            title_text += f"  <span style='font-size:11px;color:{MUTED}'>({unit})</span>"

        fig.update_layout(
            title=dict(text=title_text, font=dict(color=TEXT, size=15, family="Inter"), x=0),
            paper_bgcolor=SURFACE,
            plot_bgcolor=BG,
            font=dict(color=MUTED, family="Inter"),
            xaxis=dict(showgrid=True, gridcolor=BORDER, tickformat="%b %Y",
                       tickfont=dict(color=MUTED, size=11), zeroline=False, showline=False),
            yaxis=dict(showgrid=True, gridcolor=BORDER,
                       tickfont=dict(color=MUTED, size=11), zeroline=False, showline=False,
                       title=dict(text=unit, font=dict(color=MUTED, size=11)),
                       range=[axis_lo, axis_hi]),
            margin=dict(l=50, r=20, t=55, b=40),
            height=320, showlegend=False, hovermode="x unified",
            hoverlabel=dict(bgcolor=SURFACE2, bordercolor=BORDER,
                            font=dict(color=TEXT, family="Inter")),
        )

        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # Zone legend — shown below chart so the user reads it after seeing the chart
        if lo is not None or hi is not None:
            st.markdown(f"""
            <div class="range-legend" style="margin-top:0.25rem;margin-bottom:0.5rem">
              <span class="dot" style="background:{GREEN}"></span>Normal range
              <span class="dot" style="background:{RED};margin-left:12px"></span>High zone
              <span class="dot" style="background:{AMBER};margin-left:12px"></span>Low zone
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
        with st.expander(f"⚠️  {len(worsening)} worsening — abnormal & moving the wrong way",
                         expanded=True):
            for _, r in worsening.iterrows():
                st.markdown(
                    f"{status_pill(r['latest_status'])} &nbsp;"
                    f"**{r['test_name']}** — {r['trend']} {abs(r['change_%']):.1f}%",
                    unsafe_allow_html=True,
                )

    if not improving.empty:
        with st.expander(f"✅  {len(improving)} improving — still abnormal but trending better"):
            for _, r in improving.iterrows():
                st.markdown(
                    f"{status_pill(r['latest_status'])} &nbsp;"
                    f"**{r['test_name']}** — {r['trend']} {abs(r['change_%']):.1f}% toward normal",
                    unsafe_allow_html=True,
                )

    st.markdown('<div class="section-label">Trend Summary</div>', unsafe_allow_html=True)
    render_trends_table(trends)

    st.markdown('<div class="section-label" style="margin-top:1.75rem">Charts</div>',
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
# API KEY  (cached per session)
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
            f'<div style="font-size:0.78rem;color:{TEXT};margin-bottom:5px;line-height:1.4">'
            f'{icon} <strong>{p["patient_name"]}</strong>'
            f'<span style="color:{MUTED};margin-left:8px;font-size:0.7rem">'
            f'{p["n_reports"]} report(s)</span></div>',
            unsafe_allow_html=True,
        )

    if llm_enabled:
        st.markdown(f"""
        <div style="margin-top:1.5rem;padding:8px 10px;background:{SURFACE2};
             border:1px solid {BORDER};border-left:3px solid {ACCENT};
             border-radius:4px;font-size:0.72rem;color:{MUTED}">
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
                    render_summary_cards(snapshot)
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
          <div style="font-size:1.05rem;font-weight:600;color:#fff;margin-bottom:0.5rem">
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

            with st.expander("✏️  Manage Patient Data", expanded=False):
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

                # Reuse already-fetched patients list — avoids a second disk scan
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
                render_summary_cards(snapshot)
                render_results_table(snapshot)
                st.download_button(
                    "↓ Export Latest CSV",
                    data=snapshot.to_csv(index=False).encode("utf-8"),
                    file_name=f"{safe_name(history)}_latest.csv",
                    mime="text/csv",
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
                    use_container_width=True,
                    hide_index=True,
                )
                st.download_button(
                    "↓ Full History CSV",
                    data=history.to_csv(index=False).encode("utf-8"),
                    file_name=f"{safe_name(history)}_full_history.csv",
                    mime="text/csv",
                )

                # Manual value correction
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
         padding:0.6rem 1rem;background:{SURFACE};border:1px solid {BORDER};border-radius:6px;
         font-size:0.75rem;color:{MUTED}">
      <span>🆕 <b style="color:{TEXT}">MISSED</b> — in PDF but skipped by regex</span>
      <span>⚠️ <b style="color:{TEXT}">CORRECTED</b> — value/unit differs</span>
      <span>🔴 <b style="color:{CRIT}">CRITICAL</b> — danger zone</span>
      <span>📊 <b style="color:{RED}">HIGH</b> / <b style="color:{AMBER}">LOW</b> — out of range</span>
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
                        elif rflag == "HIGH":           rflag_html, rflag_color = "📊 HIGH",           RED
                        elif rflag == "LOW":            rflag_html, rflag_color = "📊 LOW",            AMBER

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

                # Apply decisions
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
        The <strong style="color:#fff">Longitudinal Biomarker Intelligence Platform</strong>
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
        <span style="color:{GREEN}">■</span> Green band — normal reference range<br>
        <span style="color:{RED}">■</span> Red zone — above upper limit (HIGH)<br>
        <span style="color:{AMBER}">■</span> Amber zone — below lower limit (LOW)<br>
        <span style="color:{ACCENT}">●</span> Teal dot — value within normal range<br>
        <span style="color:{RED}">●</span> Red dot — HIGH value<br>
        <span style="color:{AMBER}">●</span> Amber dot — LOW value<br>
        <span style="color:{CRIT}">●</span> Bright-red dot — CRITICAL value
      </p>
      <div class="section-label" style="margin-top:2rem">Privacy</div>
      <p style="color:{MUTED};line-height:1.85;font-size:0.85rem">
        All processing is local to the server. Patient profiles are stored as CSV files in
        <code style="color:{ACCENT}">data/patient_profiles/</code>.
        Do not commit that directory to a public repository.
      </p>
    </div>""", unsafe_allow_html=True)