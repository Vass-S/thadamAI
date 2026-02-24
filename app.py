"""
Longitudinal Biomarker Intelligence Platform
Streamlit Web App
"""

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from lab_extractor import (
    process_pdf, save_report, load_history, generate_trends,
    get_test_timeseries, list_patients, is_duplicate_file,
    delete_patient, delete_report_by_date, rename_patient,
    merge_into_patient, STORE_DIR
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
# CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Syne:wght@400;600;700;800&display=swap');

:root {
    --bg:      #0a0d12;
    --surface: #111620;
    --border:  #1e2635;
    --accent:  #00e5c3;
    --high:    #ff6b6b;
    --low:     #ffd166;
    --text:    #d4dbe8;
    --muted:   #5c6a80;
}
html, body, [class*="css"] {
    background-color: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'DM Mono', monospace !important;
}
section[data-testid="stSidebar"] {
    background-color: var(--surface) !important;
    border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] * { color: var(--text) !important; }

.bip-header {
    display: flex; align-items: baseline; gap: 12px;
    margin-bottom: 2rem; padding-bottom: 1rem;
    border-bottom: 1px solid var(--border);
}
.bip-header h1 {
    font-family: 'Syne', sans-serif !important;
    font-weight: 800 !important; font-size: 2rem !important;
    color: #fff !important; margin: 0 !important;
}
.bip-header span { font-size: 0.75rem; color: var(--accent); letter-spacing: 3px; text-transform: uppercase; }

.section-label {
    font-family: 'Syne', sans-serif; font-size: 0.65rem;
    letter-spacing: 4px; text-transform: uppercase;
    color: var(--muted); margin-bottom: 0.75rem; margin-top: 1.5rem;
}
.patient-card {
    background: var(--surface); border: 1px solid var(--border);
    border-left: 3px solid var(--accent); padding: 1.2rem 1.5rem;
    border-radius: 4px; margin-bottom: 1.5rem;
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem;
}
.patient-card .field label { font-size: 0.6rem; letter-spacing: 3px; text-transform: uppercase; color: var(--muted); display: block; }
.patient-card .field value { font-family: 'Syne', sans-serif; font-size: 1.1rem; font-weight: 700; color: #fff; }

.summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 1.5rem; }
.summary-card { background: var(--surface); border: 1px solid var(--border); padding: 1rem 1.25rem; border-radius: 4px; text-align: center; }
.summary-card .num { font-family: 'Syne', sans-serif; font-size: 2rem; font-weight: 800; line-height: 1; }
.summary-card .lbl { font-size: 0.6rem; letter-spacing: 3px; text-transform: uppercase; color: var(--muted); margin-top: 4px; }

.stButton > button {
    background: transparent !important; border: 1px solid var(--accent) !important;
    color: var(--accent) !important; font-family: 'DM Mono', monospace !important;
    font-size: 0.75rem !important; letter-spacing: 2px !important;
    text-transform: uppercase !important; border-radius: 2px !important;
    padding: 0.4rem 1.2rem !important; transition: all 0.2s ease !important;
}
.stButton > button:hover { background: var(--accent) !important; color: #000 !important; }

/* Red delete button override */
.delete-btn > button {
    border-color: var(--high) !important; color: var(--high) !important;
}
.delete-btn > button:hover { background: var(--high) !important; color: #fff !important; }

.stTabs [data-baseweb="tab-list"] { border-bottom: 1px solid var(--border) !important; gap: 0; }
.stTabs [data-baseweb="tab"] {
    background: transparent !important; border-radius: 0 !important;
    color: var(--muted) !important; font-family: 'DM Mono', monospace !important;
    font-size: 0.72rem !important; letter-spacing: 2px !important;
    text-transform: uppercase !important; padding: 0.5rem 1.5rem !important;
    border-bottom: 2px solid transparent !important;
}
.stTabs [aria-selected="true"] { color: var(--accent) !important; border-bottom: 2px solid var(--accent) !important; }

.stFileUploader > div { background: var(--surface) !important; border: 1px dashed var(--border) !important; border-radius: 4px !important; }
.stAlert { border-radius: 4px !important; }
.stDataFrame { border: 1px solid var(--border) !important; border-radius: 4px; }
.stSelectbox > div > div { background: var(--surface) !important; border: 1px solid var(--border) !important; color: var(--text) !important; border-radius: 4px !important; }
.stDownloadButton > button { background: transparent !important; border: 1px solid var(--muted) !important; color: var(--muted) !important; font-family: 'DM Mono', monospace !important; font-size: 0.7rem !important; border-radius: 2px !important; }
.streamlit-expanderHeader { background: var(--surface) !important; border: 1px solid var(--border) !important; border-radius: 4px !important; }

/* Chart background */
.stPlotlyChart { border: 1px solid var(--border); border-radius: 4px; }

#MainMenu, footer, .stDeployButton { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def safe_name(history: pd.DataFrame) -> str:
    n = history["patient_name"].iloc[0]
    return str(n).replace(" ", "_") if pd.notna(n) else "patient"


def render_patient_card(history: pd.DataFrame):
    name   = history["patient_name"].iloc[0]
    gender = history["gender"].iloc[0]
    # Current age (computed from birth_year) — fallback to age_at_test
    age_col = "current_age" if "current_age" in history.columns else "age_at_test"
    if age_col not in history.columns:
        age_col = "age"  # legacy column name
    age_val = history[age_col].dropna()
    age_display = f"{int(age_val.iloc[0])} (today)" if not age_val.empty else "—"
    dates  = history["report_date"].dropna()
    n      = len(dates.dt.strftime("%Y-%m-%d").unique()) if not dates.empty else 0
    st.markdown(f"""
    <div class="patient-card">
        <div class="field"><label>Patient Name</label><value>{name}</value></div>
        <div class="field"><label>Gender</label><value>{"Male" if str(gender).upper()=="M" else "Female"}</value></div>
        <div class="field"><label>Current Age</label><value>{age_display}</value></div>
        <div class="field"><label>Reports on File</label><value>{n}</value></div>
    </div>""", unsafe_allow_html=True)


def render_summary_cards(snapshot: pd.DataFrame):
    total    = len(snapshot)
    abnormal = snapshot["status"].str.contains("HIGH|LOW", na=False).sum()
    normal   = total - abnormal
    st.markdown(f"""
    <div class="summary-grid">
        <div class="summary-card"><div class="num" style="color:#fff">{total}</div><div class="lbl">Tests Tracked</div></div>
        <div class="summary-card"><div class="num" style="color:var(--accent)">{normal}</div><div class="lbl">Within Range</div></div>
        <div class="summary-card"><div class="num" style="color:var(--high)">{abnormal}</div><div class="lbl">Out of Range</div></div>
    </div>""", unsafe_allow_html=True)


def render_results_table(snapshot: pd.DataFrame):
    df = snapshot.copy()
    df["_sort"] = df["status"].apply(lambda s: 0 if ("HIGH" in str(s) or "LOW" in str(s)) else 1)
    df = df.sort_values(["_sort", "test_name"]).drop(columns=["_sort"])
    df["unit"] = df["unit"].astype(str).str.replace("Âµ", "µ", regex=False)
    st.dataframe(df[["test_name", "value", "unit", "status"]], width='stretch', hide_index=True)


def render_trends_table(trends: pd.DataFrame):
    """Show trends table with date columns instead of first/latest labels."""
    df = trends.copy()
    df["unit"] = df["unit"].astype(str).str.replace("Âµ", "µ", regex=False)
    # Rename columns to show actual dates
    df = df.rename(columns={
        "first_date":    "From",
        "first_value":   "Value (From)",
        "latest_date":   "To",
        "latest_value":  "Value (To)",
        "change_%":      "Δ %",
        "trend":         "Dir",
        "latest_status": "Status",
        "n_reports":     "Reports",
    })
    cols = ["test_name", "From", "Value (From)", "To", "Value (To)", "unit", "Δ %", "Dir", "Status", "Reports"]
    available = [c for c in cols if c in df.columns]
    st.dataframe(df[available], width='stretch', hide_index=True)


def render_trend_charts(history: pd.DataFrame, trends: pd.DataFrame):
    """
    Multi-select test picker → one line chart per selected test.
    Uses Plotly for styled charts matching the dark theme.
    """
    import plotly.graph_objects as go

    test_names = sorted(trends["test_name"].tolist())
    if not test_names:
        return

    selected = st.multiselect(
        "Select tests to chart",
        options=test_names,
        default=test_names[:min(3, len(test_names))],
        key="trend_chart_selector"
    )

    if not selected:
        st.info("Select one or more tests above to see their trend charts.")
        return

    for test in selected:
        ts = get_test_timeseries(history, test)
        if ts.empty or len(ts) < 2:
            continue

        unit = ts["unit"].iloc[-1] if "unit" in ts.columns else ""

        # Colour points by status
        point_colors = []
        for s in ts["status"]:
            if "HIGH" in str(s):
                point_colors.append("#ff6b6b")
            elif "LOW" in str(s):
                point_colors.append("#ffd166")
            else:
                point_colors.append("#00e5c3")

        fig = go.Figure()

        # Line
        fig.add_trace(go.Scatter(
            x=ts["report_date"],
            y=ts["value"],
            mode="lines+markers+text",
            line=dict(color="#00e5c3", width=2),
            marker=dict(color=point_colors, size=10, line=dict(color="#0a0d12", width=2)),
            text=[f"{v}" for v in ts["value"]],
            textposition="top center",
            textfont=dict(color="#d4dbe8", size=11),
            hovertemplate="%{x|%d %b %Y}<br><b>%{y}</b> " + unit + "<extra></extra>",
            name=test,
        ))

        fig.update_layout(
            title=dict(text=f"{test}  <span style='font-size:13px;color:#5c6a80'>({unit})</span>",
                       font=dict(color="#ffffff", size=15, family="Syne"), x=0),
            paper_bgcolor="#111620",
            plot_bgcolor="#0a0d12",
            font=dict(color="#5c6a80", family="DM Mono"),
            xaxis=dict(
                showgrid=True, gridcolor="#1e2635", gridwidth=1,
                tickformat="%b %Y", tickfont=dict(color="#5c6a80"),
                zeroline=False, showline=False,
            ),
            yaxis=dict(
                showgrid=True, gridcolor="#1e2635", gridwidth=1,
                tickfont=dict(color="#5c6a80"), zeroline=False, showline=False,
                title=dict(text=unit, font=dict(color="#5c6a80", size=11)),
            ),
            margin=dict(l=40, r=20, t=50, b=40),
            height=280,
            showlegend=False,
        )

        st.plotly_chart(fig, use_container_width=True)


def render_trends_section(history: pd.DataFrame, trends: pd.DataFrame, key_prefix: str = ""):
    """Full trends section: table + chart picker. key_prefix avoids widget key clashes."""
    if trends.empty:
        st.info("Need at least 2 reports for the same patient to show trends.")
        return

    render_trends_table(trends)

    # Worsening / improving callouts
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
        with st.expander(f"⚠️ {len(worsening)} Worsening Abnormal(s)", expanded=True):
            for _, row in worsening.iterrows():
                st.markdown(f"**{row['test_name']}** — {row['trend']} {abs(row['change_%'])}% · still {row['latest_status']}")
    if not improving.empty:
        with st.expander(f"✅ {len(improving)} Improving (still abnormal)"):
            for _, row in improving.iterrows():
                st.markdown(f"**{row['test_name']}** — {row['trend']} {abs(row['change_%'])}% · moving toward normal")

    st.markdown('<div class="section-label" style="margin-top:1.5rem">Line Charts</div>', unsafe_allow_html=True)
    render_trend_charts(history, trends)

    st.download_button(
        "↓ Export Trends CSV",
        data=trends.to_csv(index=False).encode("utf-8"),
        file_name=f"{safe_name(history)}_trends.csv",
        mime="text/csv",
        key=f"{key_prefix}_dl_trends"
    )


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────

with st.sidebar:
    st.markdown('<div class="section-label">Navigation</div>', unsafe_allow_html=True)
    page = st.radio("page", ["Upload Reports", "Patient Profiles", "About"], label_visibility="collapsed")

    st.markdown("---")
    st.markdown('<div class="section-label">Stored Patients</div>', unsafe_allow_html=True)
    patients = list_patients()
    if patients:
        for p in patients:
            icon = "♂" if str(p["gender"]).upper() == "M" else "♀"
            st.markdown(
                f'<div style="font-size:0.75rem;color:#d4dbe8;margin-bottom:4px">'
                f'{icon} <strong>{p["patient_name"]}</strong>'
                f'<span style="color:#5c6a80;margin-left:8px">{p["n_reports"]} report(s)</span></div>',
                unsafe_allow_html=True
            )
    else:
        st.markdown('<span style="font-size:0.75rem;color:#5c6a80">No patients yet</span>', unsafe_allow_html=True)


# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────

st.markdown("""
<div class="bip-header">
    <h1>🧬 Biomarker Intelligence</h1>
    <span>Longitudinal Health Analytics</span>
</div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════
# PAGE: UPLOAD
# ═══════════════════════════════════════════════

if page == "Upload Reports":
    st.markdown('<div class="section-label">Upload Lab Reports</div>', unsafe_allow_html=True)

    uploaded_files = st.file_uploader(
        "Drop PDF lab reports here",
        type="pdf",
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if uploaded_files and st.button("⟳  Process Reports"):
        progress = st.progress(0)
        results_by_patient = {}

        for i, uf in enumerate(uploaded_files):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uf.read())
                tmp_path = Path(tmp.name)

            # ── Duplicate check ──────────────────────────
            if is_duplicate_file(tmp_path):
                st.warning(f"⏭️ **{uf.name}** — already processed, skipping duplicate.")
                progress.progress((i + 1) / len(uploaded_files))
                continue

            df = process_pdf(tmp_path, verbose=False)

            if df.empty:
                st.warning(f"⚠️ **{uf.name}** — no data extracted. Check PDF format.")
            else:
                save_report(df)
                pid = df["patient_id"].iloc[0]
                results_by_patient.setdefault(pid, []).append(df)
                st.success(f"✓ **{uf.name}** — {len(df)} tests · {df['patient_name'].iloc[0]}")

            progress.progress((i + 1) / len(uploaded_files))

        if results_by_patient:
            st.markdown("---")
            for pid in results_by_patient:
                history = load_history(pid)
                trends  = generate_trends(history)
                render_patient_card(history)

                tab1, tab2 = st.tabs(["Latest Results", "Trends"])

                with tab1:
                    snapshot = (history.sort_values("report_date")
                                       .groupby("test_name").last().reset_index())
                    render_summary_cards(snapshot)
                    render_results_table(snapshot)
                    st.download_button(
                        "↓ Export CSV",
                        data=snapshot.to_csv(index=False).encode("utf-8"),
                        file_name=f"{safe_name(history)}_latest.csv",
                        mime="text/csv",
                        key=f"ul_snap_{pid}"
                    )

                with tab2:
                    render_trends_section(history, trends, key_prefix=f"ul_{pid}")

                st.markdown("---")

    elif not uploaded_files:
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
        </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════
# PAGE: PATIENT PROFILES
# ═══════════════════════════════════════════════

elif page == "Patient Profiles":
    st.markdown('<div class="section-label">Stored Patient Profiles</div>', unsafe_allow_html=True)

    patients = list_patients()

    if not patients:
        st.info("No patient profiles found. Upload some lab reports first.")
    else:
        patient_options = {
            f"{p['patient_name']}  ({p['n_reports']} report(s))": p["patient_id"]
            for p in patients
        }

        selected_label = st.selectbox("Select Patient", list(patient_options.keys()), label_visibility="collapsed")
        selected_pid   = patient_options[selected_label]

        history = load_history(selected_pid)

        if history.empty:
            st.error("Could not load profile.")
        else:
            render_patient_card(history)

            # ── Per-report deletion ───────────────────────
            report_dates = sorted(
                history["report_date"].dropna().dt.strftime("%Y-%m-%d").unique(),
                reverse=True
            )

            with st.expander("✏️  Manage Patient Data", expanded=False):

                # Name correction
                st.markdown('<div class="section-label">Correct patient name</div>', unsafe_allow_html=True)
                current_name = history["patient_name"].iloc[0]
                new_name = st.text_input(
                    "Patient name (edit to correct typos / OCR errors)",
                    value=current_name,
                    key="rename_input"
                )
                other_patients = [(p["patient_id"], p["patient_name"])
                                  for p in list_patients()
                                  if p["patient_id"] != selected_pid]

                col_r1, col_r2, _ = st.columns([1, 1, 4])
                with col_r1:
                    if st.button("💾 Save name", key="rename_btn"):
                        if new_name.strip() and new_name.strip().upper() != current_name:
                            rename_patient(selected_pid, new_name)
                            st.success(f"Name updated to **{new_name.strip().upper()}**.")
                            st.rerun()
                        else:
                            st.info("No change detected.")

                # Merge duplicate profiles
                if other_patients:
                    st.markdown("---")
                    st.markdown('<div class="section-label">Merge with another patient profile</div>', unsafe_allow_html=True)
                    st.caption("Use this when a misspelled name (e.g. 'Baverley' vs 'Beverley') created two profiles for the same person. All reports from this profile will be moved into the selected target and this profile will be deleted.")
                    merge_options = {f"{p[1]}  ({p[0]})": p[0] for p in other_patients}
                    merge_target_label = st.selectbox(
                        "Merge this profile INTO →",
                        options=list(merge_options.keys()),
                        key="merge_target_select"
                    )
                    merge_target_id = merge_options[merge_target_label]
                    with col_r2:
                        if st.button("🔀 Merge profiles", key="merge_btn"):
                            ok = merge_into_patient(selected_pid, merge_target_id)
                            if ok:
                                st.success("Profiles merged. Redirecting to merged profile…")
                                st.rerun()
                            else:
                                st.error("Merge failed — check both profiles exist.")

                # Delete a single report
                st.markdown("---")
                st.markdown('<div class="section-label">Delete a specific report</div>', unsafe_allow_html=True)
                del_date = st.selectbox(
                    "Choose report date to delete",
                    options=report_dates,
                    key="del_date_select"
                )
                col_a, col_b, _ = st.columns([1, 1, 4])
                with col_a:
                    if st.button("🗑 Delete this report", key="del_report_btn"):
                        ok = delete_report_by_date(selected_pid, del_date)
                        if ok:
                            st.success(f"Deleted report from {del_date}.")
                            st.rerun()
                        else:
                            st.error("Could not delete — date not found.")

                # Delete entire patient
                st.markdown("---")
                st.markdown('<div class="section-label" style="color:#ff6b6b">Delete entire patient record</div>', unsafe_allow_html=True)
                st.warning(f"This will permanently erase ALL data for **{current_name}**.")
                with col_b:
                    if st.button("⛔ Delete Patient", key="del_patient_btn"):
                        delete_patient(selected_pid)
                        st.success("Patient record deleted.")
                        st.rerun()

            # ── Main content tabs ─────────────────────────
            trends = generate_trends(history)

            tab1, tab2, tab3 = st.tabs(["Latest Results", "Trends", "Full History"])

            with tab1:
                snapshot = (history.sort_values("report_date")
                                   .groupby("test_name").last().reset_index())
                render_summary_cards(snapshot)
                render_results_table(snapshot)
                st.download_button(
                    "↓ Export CSV",
                    data=snapshot.to_csv(index=False).encode("utf-8"),
                    file_name=f"{safe_name(history)}_latest.csv",
                    mime="text/csv"
                )

            with tab2:
                render_trends_section(history, trends, key_prefix=f"pp_{selected_pid}")

            with tab3:
                st.markdown('<div class="section-label">All Test Records</div>', unsafe_allow_html=True)
                show_cols = ["report_date", "test_name", "value", "unit", "status", "source_file"]
                avail     = [c for c in show_cols if c in history.columns]
                st.dataframe(
                    history[avail].sort_values(["report_date", "test_name"], ascending=[False, True]),
                    width='stretch',
                    hide_index=True
                )
                st.download_button(
                    "↓ Full History CSV",
                    data=history.to_csv(index=False).encode("utf-8"),
                    file_name=f"{safe_name(history)}_full_history.csv",
                    mime="text/csv"
                )


# ═══════════════════════════════════════════════
# PAGE: ABOUT
# ═══════════════════════════════════════════════

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
            1. Upload PDF lab reports — patient identity is detected automatically.<br>
            2. Biomarkers are matched against a dictionary with 200+ canonical names.<br>
            3. Values are compared to sex-specific normal ranges and flagged.<br>
            4. Across multiple reports, trends, charts, and callouts are generated.<br>
            5. Duplicate uploads are detected by file hash and skipped.
        </p>
        <div class="section-label" style="margin-top:2rem">Privacy Notice</div>
        <p style="color:#d4dbe8;line-height:1.8;font-size:0.88rem">
            Reports are processed locally. Patient profiles are stored as CSV files in
            <code style="color:var(--accent)">data/patient_profiles/</code>.
            Do not commit this directory to a public repository.
        </p>
    </div>""", unsafe_allow_html=True)