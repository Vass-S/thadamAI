
"""
Longitudinal Biomarker Intelligence Platform
Streamlit Web App
"""

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from lab_extractor import (
    process_pdf, save_report, load_history, generate_trends,
    get_test_timeseries, list_patients, is_duplicate_file,
    delete_patient, delete_report_by_date, rename_patient,
    merge_into_patient, STORE_DIR
)
from llm_verifier import (
    verify_with_llm, build_diff, apply_corrections,
    save_pending_review, load_pending_reviews, delete_pending_review
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
@import url(\'https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Syne:wght@400;600;700;800&display=swap\');

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
    font-family: \'DM Mono\', monospace !important;
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
    font-family: \'Syne\', sans-serif !important;
    font-weight: 800 !important; font-size: 2rem !important;
    color: #fff !important; margin: 0 !important;
}
.bip-header span { font-size: 0.75rem; color: var(--accent); letter-spacing: 3px; text-transform: uppercase; }

.section-label {
    font-family: \'Syne\', sans-serif; font-size: 0.65rem;
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
.patient-card .field value { font-family: \'Syne\', sans-serif; font-size: 1.1rem; font-weight: 700; color: #fff; }

.summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 1.5rem; }
.summary-card { background: var(--surface); border: 1px solid var(--border); padding: 1rem 1.25rem; border-radius: 4px; text-align: center; }
.summary-card .num { font-family: \'Syne\', sans-serif; font-size: 2rem; font-weight: 800; line-height: 1; }
.summary-card .lbl { font-size: 0.6rem; letter-spacing: 3px; text-transform: uppercase; color: var(--muted); margin-top: 4px; }

.stButton > button {
    background: transparent !important; border: 1px solid var(--accent) !important;
    color: var(--accent) !important; font-family: \'DM Mono\', monospace !important;
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
    color: var(--muted) !important; font-family: \'DM Mono\', monospace !important;
    font-size: 0.72rem !important; letter-spacing: 2px !important;
    text-transform: uppercase !important; padding: 0.5rem 1.5rem !important;
    border-bottom: 2px solid transparent !important;
}
.stTabs [aria-selected="true"] { color: var(--accent) !important; border-bottom: 2px solid var(--accent) !important; }

.stFileUploader > div { background: var(--surface) !important; border: 1px dashed var(--border) !important; border-radius: 4px !important; }
.stAlert { border-radius: 4px !important; }
.stDataFrame { border: 1px solid var(--border) !important; border-radius: 4px; }
.stSelectbox > div > div { background: var(--surface) !important; border: 1px solid var(--border) !important; color: var(--text) !important; border-radius: 4px !important; }
.stDownloadButton > button { background: transparent !important; border: 1px solid var(--muted) !important; color: var(--muted) !important; font-family: \'DM Mono\', monospace !important; font-size: 0.7rem !important; border-radius: 2px !important; }
.streamlit-expanderHeader { background: var(--surface) !important; border: 1px solid var(--border) !important; border-radius: 4px !important; }

/* Chart background */
.stPlotlyChart { border: 1px solid var(--border); border-radius: 4px; }

#MainMenu, footer, .stDeployButton { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# BIOMARKER DICTIONARY LOADING AND HELPERS
# ─────────────────────────────────────────────

@st.cache_data
def load_biomarker_dictionary():
    try:
        df = pd.read_csv("Biomarker_dictionary_csv.csv")
        # Pre-parse ranges for efficiency
        df[["normal_min", "normal_max"]] = df["normal_range"].apply(lambda x: pd.Series(parse_range(x)))
        df[["optimal_min", "optimal_max"]] = df["optimal_range"].apply(lambda x: pd.Series(parse_range(x)))
        df[["high_risk_min", "high_risk_max"]] = df["high_risk_range"].apply(lambda x: pd.Series(parse_range(x)))
        df[["diseased_min", "diseased_max"]] = df["diseased_range"].apply(lambda x: pd.Series(parse_range(x)))
        return df.set_index("canonical_name")
    except FileNotFoundError:
        st.error("Biomarker_dictionary_csv.csv not found. Please ensure it\'s in the same directory as app.py.")
        return pd.DataFrame()

def parse_range(range_str):
    if pd.isna(range_str): return None, None
    range_str = str(range_str).strip()
    
    # Handle specific cases like \'<40\' or \'>=126\'
    if range_str.startswith("<="):
        return None, float(range_str[2:])
    elif range_str.startswith("<"):
        return None, float(range_str[1:])
    elif range_str.startswith(">="):
        return float(range_str[2:]), None
    elif range_str.startswith(">"):
        return float(range_str[1:]), None
    elif "–" in range_str: # Handle en-dash
        parts = range_str.split("–")
        return float(parts[0]), float(parts[1])
    elif "-" in range_str: # Handle hyphen
        parts = range_str.split("-")
        return float(parts[0]), float(parts[1])
    
    try:
        # Try to parse as a single number if no range operators
        return float(range_str), float(range_str)
    except ValueError:
        return None, None

biomarker_dictionary = load_biomarker_dictionary()

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
    
    # Color-code status column using st.column_config
    st.dataframe(
        df[["test_name", "value", "unit", "status"]],
        width=\'stretch\',
        hide_index=True,
        column_config={
            "status": st.column_config.Column(
                "Status",
                help="Biomarker status relative to normal range",
                width="small",
                # Note: Direct cell-based color-coding in st.column_config is not natively supported.
                # A common workaround is to use HTML/CSS within st.markdown or a custom component.
                # For now, we rely on existing CSS classes if applicable, or simple text.
            )
        }
    )


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
    st.dataframe(df[available], width=\'stretch\', hide_index=True)


def render_trends_section(history: pd.DataFrame, trends: pd.DataFrame, key_prefix: str):
    st.markdown(\'<div class="section-label">Trends Over Time</div>\', unsafe_allow_html=True)
    render_trends_table(trends)
    st.markdown("---")
    render_trend_charts(history, trends)


def render_trend_charts(history: pd.DataFrame, trends: pd.DataFrame):
    """
    Multi-select test picker → one line chart per selected test.
    Uses Plotly for styled charts matching the dark theme.
    """
    # import plotly.graph_objects as go # Already imported at the top

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

        # Get normal range from dictionary
        normal_min, normal_max = None, None
        if test in biomarker_dictionary.index:
            bm_info = biomarker_dictionary.loc[test]
            normal_min = bm_info[\'normal_min\']
            normal_max = bm_info[\'normal_max\']
            
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

        # Add normal range background if available
        if normal_min is not None and normal_max is not None:
            fig.add_hrect(
                y0=normal_min, y1=normal_max,
                fillcolor="#00e5c3", opacity=0.1,
                line_width=0, layer="below",
                name="Normal Range"
            )
        elif normal_min is not None:
            # If only a min is defined (e.g., >X), shade below
            # Need to get current y-axis range to determine appropriate y0
            y_min_current = ts["value"].min() if not ts.empty else normal_min * 0.9
            fig.add_hrect(
                y0=y_min_current, y1=normal_min,
                fillcolor="#ff6b6b", opacity=0.1,
                line_width=0, layer="below",
                name="Below Normal"
            )
        elif normal_max is not None:
            # If only a max is defined (e.g., <X), shade above
            y_max_current = ts["value"].max() if not ts.empty else normal_max * 1.1
            fig.add_hrect(
                y0=normal_max, y1=y_max_current,
                fillcolor="#ff6b6b", opacity=0.1,
                line_width=0, layer="below",
                name="Above Normal"
            )

        # Line
        fig.add_trace(go.Scatter(
            x=ts["report_date"],
            y=ts["value"],
            mode="lines+markers+text",
            line=dict(color="#00e5c3", width=2),
            marker=dict(color=point_colors, size=10, line=dict(color="#0a0d12", width=2)),
            text=[f"{v}" for v in ts["value"]],
            textposition="top center",
            name=test,
            hovertemplate=
                \'<b>Date</b>: %{x}<br>\
                \'<b>Value</b>: %{y:.2f} \' + unit + \'<br>\
                \'<b>Status</b>: %{text}<extra></extra>\'
        ))

        # Update layout for dark theme and better readability
        fig.update_layout(
            title=f"{test} Trend",
            xaxis_title="Report Date",
            yaxis_title=f"Value ({unit})",
            plot_bgcolor=\'rgba(0,0,0,0)\',
            paper_bgcolor=\'rgba(0,0,0,0)\',
            font=dict(color= "var(--text)", family="DM Mono"),
            hovermode="x unified",
            margin=dict(l=40, r=40, t=40, b=40),
            height=400,
            xaxis=dict(
                showgrid=True, gridcolor=\'var(--border)\',
                zeroline=True, zerolinecolor=\'var(--border)\'
            ),
            yaxis=dict(
                showgrid=True, gridcolor=\'var(--border)\',
                zeroline=True, zerolinecolor=\'var(--border)\'
            ),
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
        )
        
        # Add short description and interpretation summary to chart if available
        if test in biomarker_dictionary.index:
            bm_info = biomarker_dictionary.loc[test]
            short_desc = bm_info[\'short_description\']
            interp_summary = bm_info[\'interpretation_summary\']
            
            if pd.notna(short_desc):
                st.markdown(f"**Description**: {short_desc}")
            if pd.notna(interp_summary):
                st.markdown(f"**Interpretation**: {interp_summary}")

        st.plotly_chart(fig, use_container_width=True, config={\'displayModeBar\': False})
        st.markdown("---")


# ─────────────────────────────────────────────
# MAIN APP LOGIC
# ─────────────────────────────────────────────

# Sidebar for navigation
st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to", ["Upload Reports", "Patient Profiles", "LLM Review", "About"])

# Global settings or actions in sidebar
st.sidebar.markdown("---")
st.sidebar.header("Global Actions")

# ═══════════════════════════════════════════════
# PAGE: UPLOAD REPORTS
# ═══════════════════════════════════════════════

if page == "Upload Reports":
    st.markdown(\'<div class="section-label">Upload New Lab Reports</div>\', unsafe_allow_html=True)
    uploaded_files = st.file_uploader("Upload PDF Lab Reports", type=["pdf"], accept_multiple_files=True)

    if uploaded_files:
        for uploaded_file in uploaded_files:
            with st.status(f"Processing {uploaded_file.name}...", expanded=True) as status_box:
                if is_duplicate_file(uploaded_file.name):
                    st.info(f"Skipping {uploaded_file.name}: Duplicate file.")
                    status_box.update(label=f"Skipped {uploaded_file.name}: Duplicate", state="complete", expanded=False)
                    continue

                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                        tmp_file.write(uploaded_file.getvalue())
                        tmp_file_path = Path(tmp_file.name)

                    st.write("Extracting data with `lab_extractor`...")
                    extracted_data = process_pdf(tmp_file_path)

                    if extracted_data:
                        st.write("Saving report...")
                        save_report(extracted_data, uploaded_file.name)
                        st.success(f"Successfully processed and saved {uploaded_file.name}.")
                        status_box.update(label=f"Processed {uploaded_file.name}", state="complete", expanded=False)
                    else:
                        st.warning(f"No data extracted from {uploaded_file.name}.")
                        status_box.update(label=f"Failed {uploaded_file.name}: No data", state="error", expanded=False)

                except Exception as e:
                    st.error(f"Error processing {uploaded_file.name}: {e}")
                    status_box.update(label=f"Error {uploaded_file.name}", state="error", expanded=False)
                finally:
                    if \'tmp_file_path\' in locals() and tmp_file_path.exists():
                        tmp_file_path.unlink()
        st.rerun()

# ═══════════════════════════════════════════════
# PAGE: PATIENT PROFILES
# ═══════════════════════════════════════════════

elif page == "Patient Profiles":
    st.markdown(\'<div class="section-label">Stored Patient Profiles</div>\', unsafe_allow_html=True)

    patients = list_patients()

    if not patients:
        st.info("No patient profiles found. Upload some lab reports first.")
    else:
        patient_options = {
            f"{p[\'patient_name\']}  ({p[\'n_reports\']} report(s))": p["patient_id"]
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
                st.markdown(\'<div class="section-label">Correct patient name</div>\', unsafe_allow_html=True)
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
                    st.markdown(\'<div class="section-label">Merge with another patient profile</div>\', unsafe_allow_html=True)
                    st.caption("Use this when a misspelled name (e.g. \'Baverley\' vs \'Beverley\') created two profiles for the same person. All reports from this profile will be moved into the selected target and this profile will be deleted.")
                    merge_options = {f"{p[1]}  ({p[0]})" : p[0] for p in other_patients}
                    merge_target_label = st.selectbox(
                        "Merge this profile INTO →",
                        options=list(merge_options.keys()),
                        key="merge_target_select"
                    )
                    merge_target_id = merge_options[merge_target_label]
                    with col_r2:
                        if st.button("🔀 Merge profiles", key="merge_btn"):
                            # Using st.dialog for confirmation
                            if st.session_state.get(\'confirm_merge\', False):
                                ok = merge_into_patient(selected_pid, merge_target_id)
                                if ok:
                                    st.success("Profiles merged. Redirecting to merged profile…")
                                    st.session_state[\'confirm_merge\'] = False # Reset
                                    st.rerun()
                                else:
                                    st.error("Merge failed — check both profiles exist.")
                            else:
                                with st.dialog("Confirm Merge", key="merge_dialog"):
                                    st.write(f"Are you sure you want to merge **{current_name}** into **{merge_target_label.split(\'(\\'[0].strip()}**?")
                                    st.write("This action cannot be undone.")
                                    col_dialog_yes, col_dialog_no = st.columns(2)
                                    with col_dialog_yes:
                                        if st.button("Yes, Merge", type="primary"):
                                            st.session_state[\'confirm_merge\'] = True
                                            st.rerun()
                                    with col_dialog_no:
                                        if st.button("Cancel"):
                                            st.session_state[\'confirm_merge\'] = False
                                            st.rerun()

                # Delete a single report
                st.markdown("---")
                st.markdown(\'<div class="section-label">Delete a specific report</div>\', unsafe_allow_html=True)
                del_date = st.selectbox(
                    "Choose report date to delete",
                    options=report_dates,
                    key="del_date_select"
                )
                col_a, col_b, _ = st.columns([1, 1, 4])
                with col_a:
                    if st.button("🗑 Delete this report", key="del_report_btn"):
                        if st.session_state.get(\'confirm_delete_report\', False):
                            ok = delete_report_by_date(selected_pid, del_date)
                            if ok:
                                st.success(f"Deleted report from {del_date}.")
                                st.session_state[\'confirm_delete_report\'] = False # Reset
                                st.rerun()
                            else:
                                st.error("Could not delete — date not found.")
                        else:
                            with st.dialog("Confirm Delete Report", key="delete_report_dialog"):
                                st.write(f"Are you sure you want to delete the report from **{del_date}** for **{current_name}**?")
                                st.write("This action cannot be undone.")
                                col_dialog_yes, col_dialog_no = st.columns(2)
                                with col_dialog_yes:
                                    if st.button("Yes, Delete", type="primary"):
                                        st.session_state[\'confirm_delete_report\'] = True
                                        st.rerun()
                                with col_dialog_no:
                                    if st.button("Cancel"):
                                        st.session_state[\'confirm_delete_report\'] = False
                                        st.rerun()

                # Delete entire patient
                st.markdown("---")
                st.markdown(\'<div class="section-label" style="color:#ff6b6b">Delete entire patient record</div>\', unsafe_allow_html=True)
                st.warning(f"This will permanently erase ALL data for **{current_name}**.")
                with col_b:
                    if st.button("⛔ Delete Patient", key="del_patient_btn"):
                        if st.session_state.get(\'confirm_delete_patient\', False):
                            delete_patient(selected_pid)
                            st.success("Patient record deleted.")
                            st.session_state[\'confirm_delete_patient\'] = False # Reset
                            st.rerun()
                        else:
                            with st.dialog("Confirm Delete Patient", key="delete_patient_dialog"):
                                st.write(f"Are you absolutely sure you want to permanently erase ALL data for **{current_name}**?")
                                st.write("This action cannot be undone.")
                                col_dialog_yes, col_dialog_no = st.columns(2)
                                with col_dialog_yes:
                                    if st.button("Yes, Delete Patient", type="primary"):
                                        st.session_state[\'confirm_delete_patient\'] = True
                                        st.rerun()
                                with col_dialog_no:
                                    if st.button("Cancel"):
                                        st.session_state[\'confirm_delete_patient\'] = False
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
                st.markdown(\'<div class="section-label">All Test Records</div>\', unsafe_allow_html=True)
                show_cols = ["report_date", "test_name", "value", "unit", "status", "source_file"]
                avail     = [c for c in show_cols if c in history.columns]
                st.dataframe(
                    history[avail].sort_values(["report_date", "test_name"], ascending=[False, True]),
                    width=\'stretch\',
                    hide_index=True
                )
                st.download_button(
                    "↓ Full History CSV",
                    data=history.to_csv(index=False).encode("utf-8"),
                    file_name=f"{safe_name(history)}_full_history.csv",
                    mime="text/csv"
                )


# ═══════════════════════════════════════════════
# PAGE: LLM REVIEW
# ═══════════════════════════════════════════════

elif page == "LLM Review":
    st.markdown(\'<div class="section-label">🔍 LLM Verification Review</div>\', unsafe_allow_html=True)
    st.markdown(
        "Claude checked these reports after regex extraction and flagged potential errors or "
        "missed tests. Review each item and **Accept** or **Reject** the suggestion.",
        unsafe_allow_html=False
    )

    pending = load_pending_reviews()

    if not pending:
        st.success("✓ No pending reviews — all reports are verified.")
    else:
        for review in pending:
            pid         = review["patient_id"]
            report_date = review["report_date"]
            diff_rows   = review.get("diff", [])

            if not diff_rows:
                continue

            diff = pd.DataFrame(diff_rows)
            flagged = diff[diff["needs_review"] == True]

            if flagged.empty:
                delete_pending_review(pid, report_date)
                continue

            # Find patient name
            history = load_history(pid)
            patient_name = history["patient_name"].iloc[0] if not history.empty else pid

            with st.expander(
                f"📋 {patient_name} · {report_date} · {len(flagged)} item(s) to review",
                expanded=True
            ):
                # Show the diff table
                st.markdown(\'<div class="section-label">Flagged Values</div>\', unsafe_allow_html=True)

                accepted_keys = []
                rejected_keys = []

                for _, row in flagged.iterrows():
                    test      = row["test_name"]
                    status    = row["status"]
                    conf      = row.get("confidence", "high")
                    note      = row.get("note", "")
                    r_val     = row["regex_value"]
                    r_unit    = row.get("regex_unit", "")
                    llm_val   = row["llm_value"]
                    llm_unit  = row.get("llm_unit", "")

                    # Colour-code by status
                    if status == "missed_by_regex":
                        badge = "🆕 **MISSED**"
                        desc  = f"Claude found this test in the report but regex missed it: **{llm_val} {llm_unit}**"
                    elif status == "corrected":
                        badge = "⚠️ **CORRECTED**"
                        desc  = f"Regex extracted **{r_val} {r_unit}** → Claude says **{llm_val} {llm_unit}**"
                    else:
                        badge = "❓ **LOW CONFIDENCE**"
                        desc  = f"Regex extracted **{r_val} {r_unit}** — Claude is unsure"

                    col_info, col_accept, col_reject = st.columns([5, 1, 1])

                    with col_info:
                        st.markdown(f"{badge} &nbsp; **{test}**", unsafe_allow_html=True)
                        st.caption(desc + (f"  \\n_Note: {note}_" if note else ""))
                        if conf == "low":
                            st.caption("⚠️ Claude has low confidence in this correction")

                    widget_key = f"review_{pid}_{report_date}_{test}"
                    with col_accept:
                        if st.button("✓ Accept", key=f"acc_{widget_key}", type="primary"):
                            accepted_keys.append(test)
                    with col_reject:
                        if st.button("✗ Reject", key=f"rej_{widget_key}"):
                            rejected_keys.append(test)

                st.markdown("---")
                col_all, col_none, _ = st.columns([1.5, 1.5, 5])
                with col_all:
                    if st.button("✓ Accept All", key=f"acc_all_{pid}_{report_date}"):
                        accepted_keys = flagged["test_name"].tolist()
                with col_none:
                    if st.button("✗ Reject All", key=f"rej_all_{pid}_{report_date}"):
                        rejected_keys = flagged["test_name"].tolist()

                # Process decisions
                if accepted_keys or rejected_keys:
                    if accepted_keys:
                        # Load current saved data and apply corrections
                        current_history = load_history(pid)
                        report_df = current_history[
                            current_history["report_date"].dt.strftime("%Y-%m-%d") == report_date
                        ].copy()

                        if not report_df.empty:
                            corrected_df = apply_corrections(report_df, diff, accepted_keys)
                            corrected_df["report_date"] = report_date

                            # Remove old rows for this date and re-save with corrections
                            other_dates = current_history[
                                current_history["report_date"].dt.strftime("%Y-%m-%d") != report_date
                            ]
                            full_df = pd.concat([other_dates, corrected_df], ignore_index=True)
                            csv_path = STORE_DIR / f"{pid}.csv"
                            full_df.to_csv(csv_path, index=False)

                            st.success(
                                f"✓ Applied {len(accepted_keys)} correction(s) for "
                                f"{patient_name} · {report_date}"
                            )

                    if rejected_keys:
                        st.info(f"Rejected {len(rejected_keys)} suggestion(s) — original values kept.")

                    # Clear this pending review
                    remaining = [
                        t for t in flagged["test_name"]
                        if t not in accepted_keys and t not in rejected_keys
                    ]
                    if not remaining:
                        delete_pending_review(pid, report_date)
                        st.rerun()


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
