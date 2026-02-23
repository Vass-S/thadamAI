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
    """Render a styled HTML table for latest results."""
    rows_html = ""
    snapshot = snapshot.copy()
    snapshot["_sort"] = snapshot["status"].apply(
        lambda s: 0 if ("HIGH" in str(s) or "LOW" in str(s)) else 1
    )
    snapshot = snapshot.sort_values(["_sort", "test_name"])

    for _, row in snapshot.iterrows():
        unit   = row["unit"] if pd.notna(row.get("unit", "")) else ""
        status = status_pill(row["status"])
        rows_html += f"""
        <tr>
            <td style="color:#d4dbe8;padding:8px 12px">{row['test_name']}</td>
            <td style="color:#fff;font-weight:600;padding:8px 12px;text-align:right">{row['value']}</td>
            <td style="color:var(--muted);padding:8px 12px">{unit}</td>
            <td style="padding:8px 12px">{status}</td>
        </tr>
        """

    table = f"""
    <table style="width:100%;border-collapse:collapse;font-family:'DM Mono',monospace;font-size:0.82rem">
        <thead>
            <tr style="border-bottom:1px solid #1e2635">
                <th style="text-align:left;color:#5c6a80;padding:8px 12px;font-size:0.6rem;letter-spacing:3px;text-transform:uppercase">Test</th>
                <th style="text-align:right;color:#5c6a80;padding:8px 12px;font-size:0.6rem;letter-spacing:3px;text-transform:uppercase">Value</th>
                <th style="text-align:left;color:#5c6a80;padding:8px 12px;font-size:0.6rem;letter-spacing:3px;text-transform:uppercase">Unit</th>
                <th style="text-align:left;color:#5c6a80;padding:8px 12px;font-size:0.6rem;letter-spacing:3px;text-transform:uppercase">Status</th>
            </tr>
        </thead>
        <tbody>{rows_html}</tbody>
    </table>
    """
    st.markdown(table, unsafe_allow_html=True)


def render_trends_table(trends: pd.DataFrame):
    rows_html = ""
    for _, row in trends.iterrows():
        unit   = row["unit"] if pd.notna(row.get("unit", "")) else ""
        badge  = trend_badge(row["change_%"], row["trend"])
        status = status_pill(row["latest_status"])
        rows_html += f"""
        <tr>
            <td style="color:#d4dbe8;padding:8px 12px">{row['test_name']}</td>
            <td style="padding:8px 12px">{badge}</td>
            <td style="color:var(--muted);padding:8px 12px;text-align:right">{row['first_value']}</td>
            <td style="color:#fff;font-weight:600;padding:8px 12px;text-align:right">{row['latest_value']}</td>
            <td style="color:var(--muted);padding:8px 12px">{unit}</td>
            <td style="padding:8px 12px">{status}</td>
            <td style="color:var(--muted);padding:8px 12px;text-align:center">{int(row['n_reports'])}</td>
        </tr>
        """

    table = f"""
    <table style="width:100%;border-collapse:collapse;font-family:'DM Mono',monospace;font-size:0.82rem">
        <thead>
            <tr style="border-bottom:1px solid #1e2635">
                <th style="text-align:left;color:#5c6a80;padding:8px 12px;font-size:0.6rem;letter-spacing:3px;text-transform:uppercase">Test</th>
                <th style="text-align:left;color:#5c6a80;padding:8px 12px;font-size:0.6rem;letter-spacing:3px;text-transform:uppercase">Change</th>
                <th style="text-align:right;color:#5c6a80;padding:8px 12px;font-size:0.6rem;letter-spacing:3px;text-transform:uppercase">First</th>
                <th style="text-align:right;color:#5c6a80;padding:8px 12px;font-size:0.6rem;letter-spacing:3px;text-transform:uppercase">Latest</th>
                <th style="text-align:left;color:#5c6a80;padding:8px 12px;font-size:0.6rem;letter-spacing:3px;text-transform:uppercase">Unit</th>
                <th style="text-align:left;color:#5c6a80;padding:8px 12px;font-size:0.6rem;letter-spacing:3px;text-transform:uppercase">Status</th>
                <th style="text-align:center;color:#5c6a80;padding:8px 12px;font-size:0.6rem;letter-spacing:3px;text-transform:uppercase">Reports</th>
            </tr>
        </thead>
        <tbody>{rows_html}</tbody>
    </table>
    """
    st.markdown(table, unsafe_allow_html=True)


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
        help="Upload one or more PDF lab reports. Patient identity is detected automatically.",
        label_visibility="collapsed"
    )

    if uploaded_files:
        if st.button("⟳  Process Reports"):
            progress = st.progress(0)
            results_by_patient = {}

            for i, uf in enumerate(uploaded_files):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uf.read())
                    tmp_path = Path(tmp.name)

                with st.spinner(f"Extracting: {uf.name}"):
                    df = process_pdf(tmp_path, verbose=False)

                if df.empty:
                    st.warning(f"⚠️ No data extracted from **{uf.name}** — check PDF format.")
                else:
                    save_report(df)
                    pid = df["patient_id"].iloc[0]
                    if pid not in results_by_patient:
                        results_by_patient[pid] = []
                    results_by_patient[pid].append(df)
                    st.success(f"✓ {uf.name} — {len(df)} tests · {df['patient_name'].iloc[0]}")

                progress.progress((i + 1) / len(uploaded_files))

            st.markdown("---")

            # Show results per patient
            for pid, dfs in results_by_patient.items():
                history = load_history(pid)
                trends  = generate_trends(history)

                render_patient_card(history)

                tab1, tab2 = st.tabs(["Latest Results", "Trends"])

                with tab1:
                    snapshot = (history.sort_values("report_date")
                                       .groupby("test_name").last()
                                       .reset_index())
                    render_summary_cards(snapshot)
                    render_results_table(snapshot)

                    col1, col2 = st.columns([1, 5])
                    with col1:
                        st.download_button(
                            "↓ Export CSV",
                            data=df_to_csv_bytes(snapshot),
                            file_name=f"{history['patient_name'].iloc[0].replace(' ','_')}_latest.csv",
                            mime="text/csv"
                        )

                with tab2:
                    if trends.empty:
                        st.info("Upload more reports for the same patient to see longitudinal trends.")
                    else:
                        render_trends_table(trends)

                        # Callouts
                        abnormal_trends = trends[trends["latest_status"].str.contains("HIGH|LOW", na=False)]
                        worsening = abnormal_trends[
                            (abnormal_trends["latest_status"].str.contains("HIGH") & (abnormal_trends["change_%"] > 0)) |
                            (abnormal_trends["latest_status"].str.contains("LOW")  & (abnormal_trends["change_%"] < 0))
                        ]
                        improving = abnormal_trends[
                            (abnormal_trends["latest_status"].str.contains("HIGH") & (abnormal_trends["change_%"] < 0)) |
                            (abnormal_trends["latest_status"].str.contains("LOW")  & (abnormal_trends["change_%"] > 0))
                        ]

                        if not worsening.empty:
                            with st.expander(f"⚠️ {len(worsening)} Worsening Abnormal(s)", expanded=True):
                                for _, row in worsening.iterrows():
                                    st.markdown(
                                        f"**{row['test_name']}** — {row['trend']} {abs(row['change_%'])}% · still {row['latest_status']}"
                                    )

                        if not improving.empty:
                            with st.expander(f"✅ {len(improving)} Improving (still abnormal)"):
                                for _, row in improving.iterrows():
                                    st.markdown(
                                        f"**{row['test_name']}** — {row['trend']} {abs(row['change_%'])}% · moving toward normal"
                                    )

                        col1, col2 = st.columns([1, 5])
                        with col1:
                            st.download_button(
                                "↓ Export Trends",
                                data=df_to_csv_bytes(trends),
                                file_name=f"{history['patient_name'].iloc[0].replace(' ','_')}_trends.csv",
                                mime="text/csv"
                            )
                st.markdown("---")

    else:
        # Empty state
        st.markdown("""
        <div style="text-align:center;padding:4rem 2rem;color:#5c6a80">
            <div style="font-size:3rem;margin-bottom:1rem">📄</div>
            <div style="font-family:'Syne',sans-serif;font-size:1.1rem;color:#d4dbe8;margin-bottom:0.5rem">
                Upload lab reports to get started
            </div>
            <div style="font-size:0.8rem">
                Supports PDF reports from Hitech, Metropolis, and similar labs.<br>
                Patient identity is detected automatically from the PDF.
            </div>
        </div>
        """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# PAGE: PATIENT PROFILES
# ─────────────────────────────────────────────

elif page == "Patient Profiles":
    st.markdown('<div class="section-label">Stored Patient Profiles</div>', unsafe_allow_html=True)

    patients = list_patients()

    if not patients:
        st.info("No patient profiles found. Upload some lab reports first.")
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
        trends  = generate_trends(history)

        if history.empty:
            st.error("Could not load profile.")
        else:
            render_patient_card(history)

            tab1, tab2, tab3 = st.tabs(["Latest Results", "Trends", "Full History"])

            with tab1:
                snapshot = (history.sort_values("report_date")
                                   .groupby("test_name").last()
                                   .reset_index())
                render_summary_cards(snapshot)
                render_results_table(snapshot)

                col1, _ = st.columns([1, 5])
                with col1:
                    st.download_button(
                        "↓ Export CSV",
                        data=df_to_csv_bytes(snapshot),
                        file_name=f"{history['patient_name'].iloc[0].replace(' ','_')}_latest.csv",
                        mime="text/csv"
                    )

            with tab2:
                if trends.empty:
                    st.info("Need at least 2 reports to show trends.")
                else:
                    render_trends_table(trends)
                    col1, _ = st.columns([1, 5])
                    with col1:
                        st.download_button(
                            "↓ Export Trends",
                            data=df_to_csv_bytes(trends),
                            file_name=f"{history['patient_name'].iloc[0].replace(' ','_')}_trends.csv",
                            mime="text/csv"
                        )

            with tab3:
                st.markdown('<div class="section-label">All Test Records</div>', unsafe_allow_html=True)
                display_cols = ["report_date", "test_name", "value", "unit", "status", "source_file"]
                available = [c for c in display_cols if c in history.columns]
                st.dataframe(
                    history[available].sort_values(["report_date", "test_name"], ascending=[False, True]),
                    use_container_width=True,
                    hide_index=True
                )
                col1, _ = st.columns([1, 5])
                with col1:
                    st.download_button(
                        "↓ Full History",
                        data=df_to_csv_bytes(history),
                        file_name=f"{history['patient_name'].iloc[0].replace(' ','_')}_full_history.csv",
                        mime="text/csv"
                    )


# ─────────────────────────────────────────────
# PAGE: ABOUT
# ─────────────────────────────────────────────

elif page == "About":
    st.markdown("""
    <div style="max-width:640px">
        <div class="section-label">About this platform</div>
        <p style="color:#d4dbe8;line-height:1.8;font-size:0.88rem">
            The <strong style="color:#fff">Longitudinal Biomarker Intelligence Platform</strong> extracts
            structured data from PDF lab reports, flags out-of-range results, and tracks trends
            across multiple reports over time.
        </p>

        <div class="section-label" style="margin-top:2rem">How It Works</div>
        <p style="color:#d4dbe8;line-height:1.8;font-size:0.88rem">
            1. Upload one or more PDF lab reports.<br>
            2. The system automatically extracts patient metadata (name, age, gender, date).<br>
            3. Biomarkers are matched against a reference dictionary with 200+ canonical names and aliases.<br>
            4. Values are compared against normal ranges (sex-specific where applicable).<br>
            5. Across multiple reports, longitudinal trends are computed and surfaced.
        </p>

        <div class="section-label" style="margin-top:2rem">Supported Labs</div>
        <p style="color:#d4dbe8;line-height:1.8;font-size:0.88rem">
            Hitech Diagnostic Centre, Metropolis Healthcare, and other labs following
            similar PDF report formats. The alias dictionary can be extended for additional labs.
        </p>

        <div class="section-label" style="margin-top:2rem">Privacy Notice</div>
        <p style="color:#d4dbe8;line-height:1.8;font-size:0.88rem">
            Reports are processed locally. Patient profiles are stored as CSV files in
            <code style="color:var(--accent)">data/patient_profiles/</code>.
            Do not commit this directory to a public repository if reports contain
            identifiable health data.
        </p>
    </div>
    """, unsafe_allow_html=True)
