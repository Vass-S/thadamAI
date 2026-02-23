"""
Longitudinal Biomarker Intelligence Platform
Streamlit Web App
"""

import tempfile
import io
from pathlib import Path

import pandas as pd
import streamlit as st

from lab_extractor import (
    process_pdf, save_report, load_history,
    generate_trends, list_patients, STORE_DIR
)

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Biomarker Intelligence Platform",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# CUSTOM CSS  — dark clinical aesthetic
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Syne:wght@400;600;700;800&display=swap');

:root {
    --bg:        #0a0d12;
    --surface:   #111620;
    --border:    #1e2635;
    --accent:    #00e5c3;
    --accent2:   #ff6b6b;
    --accent3:   #ffd166;
    --text:      #d4dbe8;
    --muted:     #5c6a80;
    --normal:    #00e5c3;
    --high:      #ff6b6b;
    --low:       #ffd166;
}

html, body, [class*="css"] {
    background-color: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'DM Mono', monospace !important;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: var(--surface) !important;
    border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] * { color: var(--text) !important; }

/* Main header */
.bip-header {
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 2rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--border);
}
.bip-header h1 {
    font-family: 'Syne', sans-serif !important;
    font-weight: 800 !important;
    font-size: 2rem !important;
    letter-spacing: -0.5px;
    color: #fff !important;
    margin: 0 !important;
}
.bip-header span {
    font-size: 0.75rem;
    color: var(--accent);
    letter-spacing: 3px;
    text-transform: uppercase;
}

/* Section headers */
.section-label {
    font-family: 'Syne', sans-serif;
    font-size: 0.65rem;
    letter-spacing: 4px;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 0.75rem;
    margin-top: 1.5rem;
}

/* Patient card */
.patient-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    padding: 1.2rem 1.5rem;
    border-radius: 4px;
    margin-bottom: 1.5rem;
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
}
.patient-card .field label {
    font-size: 0.6rem;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--muted);
    display: block;
}
.patient-card .field value {
    font-family: 'Syne', sans-serif;
    font-size: 1.1rem;
    font-weight: 700;
    color: #fff;
}

/* Metric pills */
.pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 2px;
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 1px;
}
.pill-normal  { background: rgba(0,229,195,0.12); color: var(--normal); border: 1px solid rgba(0,229,195,0.3); }
.pill-high    { background: rgba(255,107,107,0.12); color: var(--high);   border: 1px solid rgba(255,107,107,0.3); }
.pill-low     { background: rgba(255,209,102,0.12); color: var(--low);    border: 1px solid rgba(255,209,102,0.3); }
.pill-neutral { background: rgba(92,106,128,0.12); color: var(--muted);  border: 1px solid rgba(92,106,128,0.3); }

/* Summary cards */
.summary-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
    margin-bottom: 1.5rem;
}
.summary-card {
    background: var(--surface);
    border: 1px solid var(--border);
    padding: 1rem 1.25rem;
    border-radius: 4px;
    text-align: center;
}
.summary-card .num {
    font-family: 'Syne', sans-serif;
    font-size: 2rem;
    font-weight: 800;
    line-height: 1;
}
.summary-card .lbl {
    font-size: 0.6rem;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--muted);
    margin-top: 4px;
}

/* Dataframe overrides */
.stDataFrame { border: 1px solid var(--border) !important; border-radius: 4px; }
.stDataFrame th {
    background: var(--surface) !important;
    font-family: 'Syne', sans-serif !important;
    font-size: 0.65rem !important;
    letter-spacing: 2px !important;
    text-transform: uppercase !important;
    color: var(--muted) !important;
}

/* Buttons */
.stButton > button {
    background: transparent !important;
    border: 1px solid var(--accent) !important;
    color: var(--accent) !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 0.75rem !important;
    letter-spacing: 2px !important;
    text-transform: uppercase !important;
    border-radius: 2px !important;
    padding: 0.4rem 1.2rem !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover {
    background: var(--accent) !important;
    color: #000 !important;
}

/* Upload zone */
.stFileUploader > div {
    background: var(--surface) !important;
    border: 1px dashed var(--border) !important;
    border-radius: 4px !important;
}

/* Alert boxes */
.stAlert { border-radius: 4px !important; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { border-bottom: 1px solid var(--border) !important; gap: 0; }
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border-radius: 0 !important;
    color: var(--muted) !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 0.72rem !important;
    letter-spacing: 2px !important;
    text-transform: uppercase !important;
    padding: 0.5rem 1.5rem !important;
    border-bottom: 2px solid transparent !important;
}
.stTabs [aria-selected="true"] {
    color: var(--accent) !important;
    border-bottom: 2px solid var(--accent) !important;
}

/* Expander */
.streamlit-expanderHeader {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 4px !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 0.8rem !important;
    color: var(--text) !important;
}

/* Selectbox / input */
.stSelectbox > div > div, .stTextInput > div > div > input {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    color: var(--text) !important;
    border-radius: 4px !important;
}

/* Hide Streamlit chrome */
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
.stDeployButton { visibility: hidden; }

/* Download button */
.stDownloadButton > button {
    background: transparent !important;
    border: 1px solid var(--muted) !important;
    color: var(--muted) !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 0.7rem !important;
    letter-spacing: 1px !important;
    text-transform: uppercase !important;
    border-radius: 2px !important;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def status_pill(status: str) -> str:
    s = str(status)
    if "HIGH" in s:
        return f'<span class="pill pill-high">{s}</span>'
    if "LOW" in s:
        return f'<span class="pill pill-low">{s}</span>'
    if "Normal" in s:
        return f'<span class="pill pill-normal">{s}</span>'
    return f'<span class="pill pill-neutral">{s}</span>'


def trend_badge(pct: float, direction: str) -> str:
    color = "#ff6b6b" if direction == "↑" else "#ffd166"
    return f'<span style="color:{color};font-weight:600">{direction} {abs(pct):.1f}%</span>'


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def render_patient_card(history: pd.DataFrame):
    name     = history["patient_name"].iloc[0]
    gender   = history["gender"].iloc[0]
    pid      = history["patient_id"].iloc[0]
    age      = history["age"].iloc[0] if "age" in history.columns else "—"
    reports  = history["report_date"].dropna()
    n        = len(reports.dt.strftime("%Y-%m-%d").unique()) if not reports.empty else 0
    gender_label = "Male" if str(gender).upper() == "M" else "Female"

    st.markdown(f"""
    <div class="patient-card">
        <div class="field"><label>Patient Name</label><value>{name}</value></div>
        <div class="field"><label>Gender</label><value>{gender_label}</value></div>
        <div class="field"><label>Age</label><value>{age}</value></div>
        <div class="field"><label>Reports on File</label><value>{n}</value></div>
    </div>
    """, unsafe_allow_html=True)


def render_summary_cards(snapshot: pd.DataFrame):
    total   = len(snapshot)
    abnormal = snapshot["status"].str.contains("HIGH|LOW", na=False).sum()
    normal  = total - abnormal
    st.markdown(f"""
    <div class="summary-grid">
        <div class="summary-card">
            <div class="num" style="color:#fff">{total}</div>
            <div class="lbl">Tests Tracked</div>
        </div>
        <div class="summary-card">
            <div class="num" style="color:var(--normal)">{normal}</div>
            <div class="lbl">Within Range</div>
        </div>
        <div class="summary-card">
            <div class="num" style="color:var(--high)">{abnormal}</div>
            <div class="lbl">Out of Range</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_results_table(snapshot: pd.DataFrame):

    snapshot = snapshot.copy()

    # Sort abnormal first
    snapshot["_sort"] = snapshot["status"].apply(
        lambda s: 0 if ("HIGH" in str(s) or "LOW" in str(s)) else 1
    )
    snapshot = snapshot.sort_values(["_sort", "test_name"])
    snapshot = snapshot.drop(columns=["_sort"])

    # Clean micro symbol
    snapshot["unit"] = snapshot["unit"].astype(str).str.replace("Âµ", "µ")

    st.dataframe(
        snapshot[["test_name", "value", "unit", "status"]],
        width="stretch",
        hide_index=True
    )


def render_trends_table(trends: pd.DataFrame):

    trends = trends.copy()
    trends["unit"] = trends["unit"].astype(str).str.replace("Âµ", "µ")

    st.dataframe(
        trends[
            [
                "test_name",
                "change_%",
                "first_value",
                "latest_value",
                "unit",
                "latest_status",
                "n_reports",
            ]
        ],
        width="stretch",
        hide_index=True
    )


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────

with st.sidebar:
    st.markdown('<div class="section-label">Navigation</div>', unsafe_allow_html=True)
    page = st.radio(
        "page",
        ["Upload Reports", "Patient Profiles", "About"],
        label_visibility="collapsed"
    )

    st.markdown("---")
    st.markdown('<div class="section-label">Stored Patients</div>', unsafe_allow_html=True)

    patients = list_patients()
    if patients:
        for p in patients:
            gender_icon = "♂" if str(p["gender"]).upper() == "M" else "♀"
            st.markdown(
                f'<div style="font-size:0.75rem;color:#d4dbe8;margin-bottom:4px">'
                f'{gender_icon} <strong>{p["patient_name"]}</strong>'
                f'<span style="color:#5c6a80;margin-left:8px">{p["n_reports"]} report(s)</span>'
                f'</div>',
                unsafe_allow_html=True
            )
    else:
        st.markdown('<span style="font-size:0.75rem;color:#5c6a80">No patients yet</span>',
                    unsafe_allow_html=True)


# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────

st.markdown("""
<div class="bip-header">
    <h1>🧬 Biomarker Intelligence</h1>
    <span>Longitudinal Health Analytics</span>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# PAGE: UPLOAD
# ─────────────────────────────────────────────

if page == "Upload Reports":
    st.markdown('<div class="section-label">Upload Lab Reports</div>', unsafe_allow_html=True)

    uploaded_files = st.file_uploader(
        "Drop PDF lab reports here",
        type="pdf",
        accept_multiple_files=True,
        help="Upload one or more PDF lab reports.",
        label_visibility="collapsed"
    )

    if uploaded_files and st.button("⟳  Process Reports"):
        progress = st.progress(0)
        results_by_patient = {}

        for i, uf in enumerate(uploaded_files):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uf.read())
                tmp_path = Path(tmp.name)

            df = process_pdf(tmp_path, verbose=False)

            if df.empty:
                st.warning(f"⚠️ No data extracted from {uf.name}")
            else:
                save_report(df)
                pid = df["patient_id"].iloc[0]
                results_by_patient.setdefault(pid, []).append(df)
                st.success(f"✓ {uf.name} — {len(df)} tests")

            progress.progress((i + 1) / len(uploaded_files))

        st.markdown("---")

        for pid in results_by_patient:
            history = load_history(pid)
            trends = generate_trends(history)

            if history.empty:
                continue

            render_patient_card(history)

            tab1, tab2 = st.tabs(["Latest Results", "Trends"])

            # ───── Latest Results ─────
            with tab1:
                snapshot = (
                    history.sort_values("report_date")
                    .groupby("test_name")
                    .last()
                    .reset_index()
                )

                render_summary_cards(snapshot)
                render_results_table(snapshot)

                # SAFE FILENAME
                raw_name = history["patient_name"].iloc[0]
                if pd.isna(raw_name):
                    raw_name = "patient"
                safe_name = str(raw_name).replace(" ", "_")

                st.download_button(
                    "↓ Export CSV",
                    data=snapshot.to_csv(index=False).encode("utf-8"),
                    file_name=f"{safe_name}_latest.csv",
                    mime="text/csv", key=f"trends_{pid}"
                )

            # ───── Trends ─────
            with tab2:
                if trends.empty:
                    st.info("Upload more reports to see trends.")
                else:
                    render_trends_table(trends)

                    raw_name = history["patient_name"].iloc[0]
                    if pd.isna(raw_name):
                        raw_name = "patient"
                    safe_name = str(raw_name).replace(" ", "_")

                    st.download_button(
                        "↓ Export Trends",
                        data=trends.to_csv(index=False).encode("utf-8"),
                        file_name=f"{safe_name}_trends.csv",
                        mime="text/csv", key=f"trends_{pid}" 
                    )

        st.markdown("---")

# ─────────────────────────────────────────────
# PAGE: PATIENT PROFILES
# ─────────────────────────────────────────────

elif page == "Patient Profiles":
    st.markdown('<div class="section-label">Stored Patient Profiles</div>', unsafe_allow_html=True)

    patients = list_patients()

    if not patients:
        st.info("No patient profiles found.")
    else:
        patient_options = {
            f"{p['patient_name']} ({p['n_reports']} report(s))": p["patient_id"]
            for p in patients
        }

        selected_label = st.selectbox(
            "Select Patient",
            list(patient_options.keys()),
            label_visibility="collapsed"
        )
        selected_pid = patient_options[selected_label]

        history = load_history(selected_pid)
        trends = generate_trends(history)

        if history.empty:
            st.error("Could not load profile.")
        else:
            render_patient_card(history)

            tab1, tab2, tab3 = st.tabs(["Latest Results", "Trends", "Full History"])

            # ───── Latest ─────
            with tab1:
                snapshot = (
                    history.sort_values("report_date")
                    .groupby("test_name")
                    .last()
                    .reset_index()
                )

                render_summary_cards(snapshot)
                render_results_table(snapshot)

                raw_name = history["patient_name"].iloc[0]
                if pd.isna(raw_name):
                    raw_name = "patient"
                safe_name = str(raw_name).replace(" ", "_")

                st.download_button(
                    "↓ Export CSV",
                    data=snapshot.to_csv(index=False).encode("utf-8"),
                    file_name=f"{safe_name}_latest.csv",
                    mime="text/csv"
                )

            # ───── Trends ─────
            with tab2:
                if trends.empty:
                    st.info("Need at least 2 reports for trends.")
                else:
                    render_trends_table(trends)

                    raw_name = history["patient_name"].iloc[0]
                    if pd.isna(raw_name):
                        raw_name = "patient"
                    safe_name = str(raw_name).replace(" ", "_")

                    st.download_button(
                        "↓ Export Trends",
                        data=trends.to_csv(index=False).encode("utf-8"),
                        file_name=f"{safe_name}_trends.csv",
                        mime="text/csv", 
                    )

            # ───── Full History ─────
            with tab3:
                st.dataframe(history, use_container_width=True)

                raw_name = history["patient_name"].iloc[0]
                if pd.isna(raw_name):
                    raw_name = "patient"
                safe_name = str(raw_name).replace(" ", "_")

                st.download_button(
                    "↓ Full History",
                    data=history.to_csv(index=False).encode("utf-8"),
                    file_name=f"{safe_name}_full_history.csv",
                    mime="text/csv"
                )
