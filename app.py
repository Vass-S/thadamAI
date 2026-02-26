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
    merge_into_patient, patch_record, STORE_DIR
)
from llm_verifier import (
    verify_with_llm, build_diff, apply_corrections,
    get_metadata_corrections,
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
html, body, [class*="css"] { background-color: var(--bg) !important; color: var(--text) !important; font-family: 'DM Mono', monospace !important; }
section[data-testid="stSidebar"] { background-color: var(--surface) !important; border-right: 1px solid var(--border) !important; }
section[data-testid="stSidebar"] * { color: var(--text) !important; }
.bip-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 1px solid var(--border); }
.bip-header h1 { font-family: 'Syne', sans-serif !important; font-weight: 800 !important; font-size: 2rem !important; color: #fff !important; margin: 0 !important; }
.bip-header span { font-size: 0.75rem; color: var(--accent); letter-spacing: 3px; text-transform: uppercase; }
.section-label { font-family: 'Syne', sans-serif; font-size: 0.65rem; letter-spacing: 4px; text-transform: uppercase; color: var(--muted); margin-bottom: 0.75rem; margin-top: 1.5rem; }
.patient-card { background: var(--surface); border: 1px solid var(--border); border-left: 3px solid var(--accent); padding: 1.2rem 1.5rem; border-radius: 4px; margin-bottom: 1.5rem; display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; }
.patient-card .field label { font-size: 0.6rem; letter-spacing: 3px; text-transform: uppercase; color: var(--muted); display: block; }
.patient-card .field value { font-family: 'Syne', sans-serif; font-size: 1.1rem; font-weight: 700; color: #fff; }
.summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 1.5rem; }
.summary-card { background: var(--surface); border: 1px solid var(--border); padding: 1rem 1.25rem; border-radius: 4px; text-align: center; }
.summary-card .num { font-family: 'Syne', sans-serif; font-size: 2rem; font-weight: 800; line-height: 1; }
.summary-card .lbl { font-size: 0.6rem; letter-spacing: 3px; text-transform: uppercase; color: var(--muted); margin-top: 4px; }
.stButton > button { background: transparent !important; border: 1px solid var(--accent) !important; color: var(--accent) !important; font-family: 'DM Mono', monospace !important; font-size: 0.75rem !important; letter-spacing: 2px !important; text-transform: uppercase !important; border-radius: 2px !important; padding: 0.4rem 1.2rem !important; transition: all 0.2s ease !important; }
.stButton > button:hover { background: var(--accent) !important; color: #000 !important; }
.stTabs [data-baseweb="tab-list"] { border-bottom: 1px solid var(--border) !important; gap: 0; }
.stTabs [data-baseweb="tab"] { background: transparent !important; border-radius: 0 !important; color: var(--muted) !important; font-family: 'DM Mono', monospace !important; font-size: 0.72rem !important; letter-spacing: 2px !important; text-transform: uppercase !important; padding: 0.5rem 1.5rem !important; border-bottom: 2px solid transparent !important; }
.stTabs [aria-selected="true"] { color: var(--accent) !important; border-bottom: 2px solid var(--accent) !important; }
.stFileUploader > div { background: var(--surface) !important; border: 1px dashed var(--border) !important; border-radius: 4px !important; }
.stDataFrame { border: 1px solid var(--border) !important; border-radius: 4px; }
.stSelectbox > div > div { background: var(--surface) !important; border: 1px solid var(--border) !important; color: var(--text) !important; border-radius: 4px !important; }
.stDownloadButton > button { background: transparent !important; border: 1px solid var(--muted) !important; color: var(--muted) !important; font-family: 'DM Mono', monospace !important; font-size: 0.7rem !important; border-radius: 2px !important; }
.streamlit-expanderHeader { background: var(--surface) !important; border: 1px solid var(--border) !important; border-radius: 4px !important; }
.stPlotlyChart { border: 1px solid var(--border); border-radius: 4px; }
#MainMenu, footer, .stDeployButton { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# BIOMARKER DICTIONARY
# ─────────────────────────────────────────────

def _parse_range(range_str):
    if pd.isna(range_str):
        return None, None
    s = str(range_str).strip()
    if not s or s.lower() == "nan":
        return None, None
    try:
        if s.startswith("<="):   return None, float(s[2:])
        if s.startswith("<"):    return None, float(s[1:])
        if s.startswith(">="):   return float(s[2:]), None
        if s.startswith(">"):    return float(s[1:]), None
        for sep in ["\u2013", "-"]:
            if sep in s:
                parts = s.split(sep, 1)
                return float(parts[0].strip()), float(parts[1].strip())
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
        st.error("Biomarker_dictionary_csv.csv not found.")
        return pd.DataFrame()

    if "canonical_name" not in df.columns:
        st.error("CSV missing canonical_name column.")
        return pd.DataFrame()

    range_cols = {
        "normal_range":    ("normal_min",    "normal_max"),
        "optimal_range":   ("optimal_min",   "optimal_max"),
        "high_risk_range": ("high_risk_min", "high_risk_max"),
        "diseased_range":  ("diseased_min",  "diseased_max"),
    }
    for src_col, (mn, mx) in range_cols.items():
        if src_col in df.columns:
            parsed = df[src_col].apply(lambda x: pd.Series(_parse_range(x), index=[mn, mx]))
            df[mn] = parsed[mn]
            df[mx] = parsed[mx]
        else:
            df[mn] = None
            df[mx] = None

    for col in ["short_description", "interpretation_summary", "category",
                "related_conditions", "common_panels"]:
        if col not in df.columns:
            df[col] = None

    return df.set_index("canonical_name")


biomarker_dictionary = load_biomarker_dictionary()


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def safe_name(history):
    n = history["patient_name"].iloc[0]
    return str(n).replace(" ", "_") if pd.notna(n) else "patient"


def render_patient_card(history):
    name   = history["patient_name"].iloc[0]
    gender = history["gender"].iloc[0]
    age_col = "current_age" if "current_age" in history.columns else "age_at_test"
    age_val = history[age_col].dropna()
    age_display = f"{int(age_val.iloc[0])} (today)" if not age_val.empty else "—"
    dates = history["report_date"].dropna()
    n = len(dates.dt.strftime("%Y-%m-%d").unique()) if not dates.empty else 0
    st.markdown(f"""
    <div class="patient-card">
        <div class="field"><label>Patient Name</label><value>{name}</value></div>
        <div class="field"><label>Gender</label><value>{"Male" if str(gender).upper()=="M" else "Female"}</value></div>
        <div class="field"><label>Current Age</label><value>{age_display}</value></div>
        <div class="field"><label>Reports on File</label><value>{n}</value></div>
    </div>""", unsafe_allow_html=True)


def render_summary_cards(snapshot):
    total    = len(snapshot)
    abnormal = snapshot["status"].str.contains("HIGH|LOW", na=False).sum()
    normal   = total - abnormal
    st.markdown(f"""
    <div class="summary-grid">
        <div class="summary-card"><div class="num" style="color:#fff">{total}</div><div class="lbl">Tests Tracked</div></div>
        <div class="summary-card"><div class="num" style="color:var(--accent)">{normal}</div><div class="lbl">Within Range</div></div>
        <div class="summary-card"><div class="num" style="color:var(--high)">{abnormal}</div><div class="lbl">Out of Range</div></div>
    </div>""", unsafe_allow_html=True)


def render_results_table(snapshot):
    df = snapshot.copy()
    df["_sort"] = df["status"].apply(lambda s: 0 if ("HIGH" in str(s) or "LOW" in str(s)) else 1)
    df = df.sort_values(["_sort", "test_name"]).drop(columns=["_sort"])
    df["unit"] = df["unit"].astype(str).str.replace("Âµ", "µ", regex=False)
    st.dataframe(df[["test_name", "value", "unit", "status"]], width="stretch", hide_index=True)


def render_trends_table(trends):
    df = trends.copy()
    df["unit"] = df["unit"].astype(str).str.replace("Âµ", "µ", regex=False)
    df = df.rename(columns={
        "first_date": "From", "first_value": "Value (From)",
        "latest_date": "To", "latest_value": "Value (To)",
        "change_%": "Δ %", "trend": "Dir",
        "latest_status": "Status", "n_reports": "Reports",
    })
    cols = ["test_name", "From", "Value (From)", "To", "Value (To)", "unit", "Δ %", "Dir", "Status", "Reports"]
    st.dataframe(df[[c for c in cols if c in df.columns]], width="stretch", hide_index=True)


def render_trend_charts(history, trends, key_prefix=""):
    test_names = sorted(trends["test_name"].tolist())
    if not test_names:
        return
    selected = st.multiselect(
        "Select tests to chart",
        options=test_names,
        default=test_names[:min(3, len(test_names))],
        key=f"trend_chart_{key_prefix}",
    )
    if not selected:
        st.info("Select one or more tests above to see their trend charts.")
        return

    for test in selected:
        ts = get_test_timeseries(history, test)
        if ts.empty or len(ts) < 2:
            continue
        unit = str(ts["unit"].iloc[-1]) if "unit" in ts.columns else ""
        if unit in ("nan", "None", "NaN"):
            unit = ""

        normal_min = normal_max = short_desc = interp_summary = None
        if not biomarker_dictionary.empty and test in biomarker_dictionary.index:
            bm = biomarker_dictionary.loc[test]
            if isinstance(bm, pd.DataFrame):
                bm = bm.iloc[0]
            normal_min     = bm.get("normal_min")
            normal_max     = bm.get("normal_max")
            short_desc     = bm.get("short_description")
            interp_summary = bm.get("interpretation_summary")

        point_colors = []
        for s in ts["status"]:
            if "HIGH" in str(s):   point_colors.append("#ff6b6b")
            elif "LOW" in str(s):  point_colors.append("#ffd166")
            else:                  point_colors.append("#00e5c3")

        fig = go.Figure()

        if normal_min is not None and normal_max is not None:
            fig.add_hrect(y0=normal_min, y1=normal_max, fillcolor="#00e5c3",
                          opacity=0.08, line_width=0, layer="below")
        elif normal_max is not None:
            y_top = max(ts["value"].max() * 1.1, normal_max * 1.1)
            fig.add_hrect(y0=normal_max, y1=y_top, fillcolor="#ff6b6b",
                          opacity=0.08, line_width=0, layer="below")
        elif normal_min is not None:
            y_bot = min(ts["value"].min() * 0.9, normal_min * 0.9)
            fig.add_hrect(y0=y_bot, y1=normal_min, fillcolor="#ff6b6b",
                          opacity=0.08, line_width=0, layer="below")

        fig.add_trace(go.Scatter(
            x=ts["report_date"], y=ts["value"],
            mode="lines+markers+text",
            line=dict(color="#00e5c3", width=2),
            marker=dict(color=point_colors, size=10, line=dict(color="#0a0d12", width=2)),
            text=[str(v) for v in ts["value"]],
            textposition="top center",
            textfont=dict(color="#d4dbe8", size=11),
            hovertemplate="%{x|%d %b %Y}<br><b>%{y}</b> " + unit + "<extra></extra>",
            name=test,
        ))
        fig.update_layout(
            title=dict(text=f"{test}  <span style='font-size:13px;color:#5c6a80'>({unit})</span>",
                       font=dict(color="#ffffff", size=15, family="Syne"), x=0),
            paper_bgcolor="#111620", plot_bgcolor="#0a0d12",
            font=dict(color="#5c6a80", family="DM Mono"),
            xaxis=dict(showgrid=True, gridcolor="#1e2635", tickformat="%b %Y",
                       tickfont=dict(color="#5c6a80"), zeroline=False, showline=False),
            yaxis=dict(showgrid=True, gridcolor="#1e2635",
                       tickfont=dict(color="#5c6a80"), zeroline=False, showline=False,
                       title=dict(text=unit, font=dict(color="#5c6a80", size=11))),
            margin=dict(l=40, r=20, t=50, b=40),
            height=300, showlegend=False, hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        if short_desc and pd.notna(short_desc):
            st.caption(f"**What it measures:** {short_desc}")
        if interp_summary and pd.notna(interp_summary):
            st.caption(f"**Interpretation:** {interp_summary}")
        st.markdown("---")


def render_trends_section(history, trends, key_prefix=""):
    if trends.empty:
        st.info("Need at least 2 reports for the same patient to show trends.")
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
        with st.expander(f"⚠️ {len(worsening)} Worsening Abnormal(s)", expanded=True):
            for _, row in worsening.iterrows():
                st.markdown(f"**{row['test_name']}** — {row['trend']} {abs(row['change_%'])}% · still {row['latest_status']}")
    if not improving.empty:
        with st.expander(f"✅ {len(improving)} Improving (still abnormal)"):
            for _, row in improving.iterrows():
                st.markdown(f"**{row['test_name']}** — {row['trend']} {abs(row['change_%'])}% · moving toward normal")

    render_trends_table(trends)
    st.markdown('<div class="section-label" style="margin-top:1.5rem">Line Charts</div>', unsafe_allow_html=True)
    render_trend_charts(history, trends, key_prefix=key_prefix)
    st.download_button(
        "↓ Export Trends CSV",
        data=trends.to_csv(index=False).encode("utf-8"),
        file_name=f"{safe_name(history)}_trends.csv",
        mime="text/csv",
        key=f"{key_prefix}_dl_trends",
    )


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────

with st.sidebar:
    st.markdown('<div class="section-label">Navigation</div>', unsafe_allow_html=True)
    pending = load_pending_reviews()
    review_label = f"🔍 LLM Review ({len(pending)})" if pending else "🔍 LLM Review"
    page = st.radio("page",
                    ["Upload Reports", "Patient Profiles", review_label, "About"],
                    label_visibility="collapsed")
    if page.startswith("🔍 LLM Review"):
        page = "LLM Review"
    st.markdown("---")
    st.markdown('<div class="section-label">Stored Patients</div>', unsafe_allow_html=True)
    for p in list_patients():
        icon = "♂" if str(p["gender"]).upper() == "M" else "♀"
        st.markdown(
            f'<div style="font-size:0.75rem;color:#d4dbe8;margin-bottom:4px">'
            f'{icon} <strong>{p["patient_name"]}</strong>'
            f'<span style="color:#5c6a80;margin-left:8px">{p["n_reports"]} report(s)</span></div>',
            unsafe_allow_html=True)

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

    api_key = ""
    if hasattr(st, "secrets"):
        api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    llm_enabled = bool(api_key)

    if llm_enabled:
        st.caption("🤖 LLM verification enabled — Claude will check extracted values after processing.")
    else:
        st.caption("⚪ LLM verification disabled — add ANTHROPIC_API_KEY to Streamlit secrets to enable.")

    uploaded_files = st.file_uploader("Drop PDF lab reports here", type="pdf",
                                       accept_multiple_files=True, label_visibility="collapsed")

    # Date override inputs — shown before processing so user can fix missing dates
    if uploaded_files:
        with st.expander("⚙️ Date overrides (use if a report's date wasn't detected)", expanded=False):
            st.caption("Leave blank to use the date extracted from the PDF. "
                       "Fill in only if the Trends tab shows 'Need at least 2 reports' "
                       "even after uploading multiple reports for the same patient.")
            date_overrides = {}
            for uf in uploaded_files:
                v = st.text_input(
                    f"{uf.name}  (YYYY-MM-DD)",
                    value="",
                    key=f"date_override_{uf.name}",
                    placeholder="e.g. 2024-11-28",
                )
                if v.strip():
                    date_overrides[uf.name] = v.strip()
    else:
        date_overrides = {}

    if uploaded_files and st.button("⟳  Process Reports"):
        progress = st.progress(0)
        results_by_patient = {}

        for i, uf in enumerate(uploaded_files):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uf.read())
                tmp_path = Path(tmp.name)

            if is_duplicate_file(tmp_path):
                st.warning(f"⏭️ **{uf.name}** — already processed, skipping.")
                progress.progress((i + 1) / len(uploaded_files))
                continue

            df, raw_text = process_pdf(tmp_path, verbose=False)

            if df.empty:
                st.warning(f"⚠️ **{uf.name}** — no data extracted.")
                progress.progress((i + 1) / len(uploaded_files))
                continue

            # ── Apply date override if user supplied one or extraction missed it ──
            extracted_date = df["report_date"].iloc[0] if not df.empty else ""
            override = date_overrides.get(uf.name, "").strip()
            if override:
                df["report_date"] = override
                st.caption(f"📅 Date override applied for **{uf.name}**: {override}")
            elif not extracted_date:
                st.warning(
                    f"⚠️ **{uf.name}** — could not detect report date. "
                    f"Expand **Date overrides** above and enter the date manually, "
                    f"then re-upload."
                )

            ocr_used = df.get("ocr_extracted", pd.Series([False])).iloc[0]
            pid  = df["patient_id"].iloc[0]
            name = df["patient_name"].iloc[0]

            if llm_enabled:
                with st.spinner(f"🤖 Claude is verifying {uf.name}…"):
                    llm_result = verify_with_llm(raw_text, df, api_key=api_key)
                if llm_result.get("error"):
                    st.warning(f"⚠️ LLM check failed for **{uf.name}**: {llm_result['error']}")
                    save_report(df)
                else:
                    diff         = build_diff(df, llm_result)
                    meta_corr    = get_metadata_corrections(df, llm_result)
                    meta_issues  = meta_corr.get("metadata_issues", [])

                    # Auto-apply date correction immediately if regex missed it
                    if meta_corr.get("date_correction") and not override:
                        df["report_date"] = meta_corr["date_correction"]
                        st.caption(f"📅 Date found by Claude ({meta_corr.get('date_source','')}):"
                                   f" **{meta_corr['date_correction']}**")
                        meta_corr["date_correction"] = None   # already applied

                    needs_review_df = diff[diff["needs_review"]] if not diff.empty else pd.DataFrame()
                    n_corrections   = len(needs_review_df)
                    has_meta        = bool(meta_corr.get("date_correction") or
                                          meta_corr.get("name_correction") or meta_issues)

                    if n_corrections == 0 and not has_meta:
                        st.success(f"✓ **{uf.name}** — {len(df)} tests · {name} · 🤖 all values confirmed")
                        df["llm_verified"] = True
                        save_report(df)
                    else:
                        save_report(df)
                        save_pending_review(pid, df["report_date"].iloc[0],
                                            diff, raw_text, meta_corr)
                        parts = []
                        if n_corrections:
                            parts.append(f"{n_corrections} value/unit flag(s)")
                        if meta_issues:
                            parts.append(f"{len(meta_issues)} metadata issue(s)")
                        if meta_corr.get("date_correction") or meta_corr.get("name_correction"):
                            parts.append("metadata correction(s)")
                        st.success(f"✓ **{uf.name}** — {len(df)} tests · {name}")
                        st.warning(f"🔍 **{', '.join(parts)} need review** — see LLM Review in sidebar.")
            else:
                save_report(df)
                st.success(f"✓ **{uf.name}** — {len(df)} tests · {name}")

            if ocr_used:
                st.caption("📷 OCR mode — verify hormone/thyroid values against original.")

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
                    snapshot = history.sort_values("report_date").groupby("test_name").last().reset_index()
                    render_summary_cards(snapshot)
                    render_results_table(snapshot)
                    st.download_button("↓ Export CSV",
                        data=snapshot.to_csv(index=False).encode("utf-8"),
                        file_name=f"{safe_name(history)}_latest.csv", mime="text/csv",
                        key=f"ul_snap_{pid}")
                with tab2:
                    render_trends_section(history, trends, key_prefix=f"ul_{pid}")
                st.markdown("---")

    elif not uploaded_files:
        st.markdown("""
        <div style="text-align:center;padding:4rem 2rem;color:#5c6a80">
            <div style="font-size:3rem;margin-bottom:1rem">📄</div>
            <div style="font-family:'Syne',sans-serif;font-size:1.1rem;color:#d4dbe8;margin-bottom:0.5rem">Upload lab reports to get started</div>
            <div style="font-size:0.8rem">Supports Hitech, Kauvery, Metropolis and similar labs.</div>
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
        patient_options = {f"{p['patient_name']}  ({p['n_reports']} report(s))": p["patient_id"]
                           for p in patients}
        selected_label = st.selectbox("Select Patient", list(patient_options.keys()),
                                       label_visibility="collapsed")
        selected_pid = patient_options[selected_label]
        history = load_history(selected_pid)

        if history.empty:
            st.error("Could not load profile.")
        else:
            render_patient_card(history)
            report_dates = sorted(
                history["report_date"].dropna().dt.strftime("%Y-%m-%d").unique(), reverse=True)

            with st.expander("✏️  Manage Patient Data", expanded=False):
                st.markdown('<div class="section-label">Correct patient name</div>', unsafe_allow_html=True)
                current_name = history["patient_name"].iloc[0]
                new_name = st.text_input("Patient name", value=current_name, key="rename_input")
                other_patients = [(p["patient_id"], p["patient_name"]) for p in list_patients()
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

                if other_patients:
                    st.markdown("---")
                    st.markdown('<div class="section-label">Merge with another profile</div>', unsafe_allow_html=True)
                    merge_options = {f"{p[1]}  ({p[0]})": p[0] for p in other_patients}
                    merge_target_label = st.selectbox("Merge INTO →", list(merge_options.keys()),
                                                       key="merge_target_select")
                    merge_target_id = merge_options[merge_target_label]
                    with col_r2:
                        if st.button("🔀 Merge profiles", key="merge_btn"):
                            ok = merge_into_patient(selected_pid, merge_target_id)
                            if ok:
                                st.success("Profiles merged.")
                                st.rerun()
                            else:
                                st.error("Merge failed.")

                st.markdown("---")
                st.markdown('<div class="section-label">Delete a specific report</div>', unsafe_allow_html=True)
                del_date = st.selectbox("Report date to delete", options=report_dates, key="del_date_select")
                col_a, col_b, _ = st.columns([1, 1, 4])
                with col_a:
                    if st.button("🗑 Delete this report", key="del_report_btn"):
                        ok = delete_report_by_date(selected_pid, del_date)
                        if ok:
                            st.success(f"Deleted report from {del_date}.")
                            st.rerun()
                        else:
                            st.error("Could not delete.")

                st.markdown("---")
                st.markdown('<div class="section-label" style="color:#ff6b6b">Delete entire patient record</div>',
                            unsafe_allow_html=True)
                st.warning(f"This will permanently erase ALL data for **{current_name}**.")
                with col_b:
                    if st.button("⛔ Delete Patient", key="del_patient_btn"):
                        delete_patient(selected_pid)
                        st.success("Patient record deleted.")
                        st.rerun()

            trends = generate_trends(history)
            tab1, tab2, tab3 = st.tabs(["Latest Results", "Trends", "Full History"])

            with tab1:
                snapshot = history.sort_values("report_date").groupby("test_name").last().reset_index()
                render_summary_cards(snapshot)
                render_results_table(snapshot)
                st.download_button("↓ Export CSV",
                    data=snapshot.to_csv(index=False).encode("utf-8"),
                    file_name=f"{safe_name(history)}_latest.csv", mime="text/csv")

            with tab2:
                render_trends_section(history, trends, key_prefix=f"pp_{selected_pid}")

            with tab3:
                st.markdown('<div class="section-label">All Test Records</div>', unsafe_allow_html=True)
                show_cols = ["report_date", "test_name", "value", "unit", "status", "source_file"]
                avail = [c for c in show_cols if c in history.columns]
                st.dataframe(history[avail].sort_values(["report_date", "test_name"],
                             ascending=[False, True]), use_container_width=True, hide_index=True)
                st.download_button("↓ Full History CSV",
                    data=history.to_csv(index=False).encode("utf-8"),
                    file_name=f"{safe_name(history)}_full_history.csv", mime="text/csv")

                # ── Manual edit: fix any individual result ────────────────
                st.markdown("---")
                st.markdown('<div class="section-label">✏️ Manually Correct a Result</div>',
                            unsafe_allow_html=True)
                st.caption(
                    "Use this when both regex and Claude got a value wrong or uncertain. "
                    "Pick the report date and test, enter the correct value and unit, "
                    "and the status will be re-flagged automatically."
                )

                edit_col1, edit_col2 = st.columns(2)
                with edit_col1:
                    edit_date = st.selectbox(
                        "Report date",
                        options=report_dates,
                        key=f"edit_date_{selected_pid}"
                    )
                with edit_col2:
                    date_tests = sorted(
                        history[
                            history["report_date"].dt.strftime("%Y-%m-%d") == edit_date
                        ]["test_name"].unique().tolist()
                    )
                    edit_test = st.selectbox(
                        "Test to correct",
                        options=date_tests,
                        key=f"edit_test_{selected_pid}"
                    )

                # Pre-fill current stored value and unit
                current_row = history[
                    (history["report_date"].dt.strftime("%Y-%m-%d") == edit_date) &
                    (history["test_name"] == edit_test)
                ]
                cur_val  = float(current_row["value"].iloc[0])  if not current_row.empty else 0.0
                cur_unit = str(current_row["unit"].iloc[0])      if not current_row.empty else ""
                cur_stat = str(current_row["status"].iloc[0])    if not current_row.empty else ""
                if cur_unit in ("nan", "None"):
                    cur_unit = ""

                val_col, unit_col, btn_col = st.columns([2, 2, 1])
                with val_col:
                    new_val = st.number_input(
                        f"Correct value  (current: {cur_val})",
                        value=cur_val,
                        format="%.4f",
                        key=f"edit_val_{selected_pid}_{edit_date}_{edit_test}"
                    )
                with unit_col:
                    new_unit = st.text_input(
                        f"Correct unit  (current: {cur_unit or '—'})",
                        value=cur_unit,
                        key=f"edit_unit_{selected_pid}_{edit_date}_{edit_test}"
                    )
                with btn_col:
                    st.markdown("<div style='margin-top:1.75rem'></div>", unsafe_allow_html=True)
                    if st.button("💾 Save", key=f"edit_save_{selected_pid}_{edit_date}_{edit_test}"):
                        if abs(new_val - cur_val) > 0.0001 or new_unit.strip() != cur_unit.strip():
                            ok = patch_record(
                                selected_pid, edit_date, edit_test,
                                new_value=new_val, new_unit=new_unit.strip()
                            )
                            if ok:
                                st.success(f"✓ Saved: **{edit_test}** = {new_val} {new_unit.strip()}")
                                st.rerun()
                            else:
                                st.error("Could not find that record to update.")
                        else:
                            st.info("No change detected.")


# ═══════════════════════════════════════════════
# PAGE: LLM REVIEW
# ═══════════════════════════════════════════════

elif page == "LLM Review":
    st.markdown('<div class="section-label">🔍 LLM Verification Review</div>', unsafe_allow_html=True)
    st.markdown(
        "Claude audited each report for **missing fields**, **wrong/missing units**, "
        "**date detection**, **out-of-range values**, and **missed tests**. "
        "Nothing is changed automatically — every flag needs your approval."
    )

    # Legend
    st.markdown("""
    <div style="display:flex;gap:1.5rem;margin-bottom:1rem;flex-wrap:wrap;font-size:0.75rem;">
      <span>🆕 <b>MISSED</b> — test found in PDF but regex skipped it</span>
      <span>⚠️ <b>CORRECTED</b> — value or unit differs from raw text</span>
      <span>🔴 <b>CRITICAL</b> — value in critical danger zone</span>
      <span>📊 <b>OUT OF RANGE</b> — above or below reference range</span>
      <span>📋 <b>METADATA</b> — missing date, name, gender, or units</span>
      <span>❓ <b>LOW CONFIDENCE</b> — Claude unsure, needs human check</span>
    </div>
    """, unsafe_allow_html=True)

    pending = load_pending_reviews()
    if not pending:
        st.success("✓ No pending reviews — all reports are verified.")
    else:
        for review in pending:
            pid          = review["patient_id"]
            report_date  = review["report_date"]
            diff_rows    = review.get("diff", [])
            meta_corr    = review.get("meta_corrections", {})

            history      = load_history(pid)
            patient_name = history["patient_name"].iloc[0] if not history.empty else pid

            diff    = pd.DataFrame(diff_rows) if diff_rows else pd.DataFrame()
            flagged = diff[diff["needs_review"] == True] if not diff.empty else pd.DataFrame()

            meta_issues      = meta_corr.get("metadata_issues", [])
            date_correction  = meta_corr.get("date_correction")
            name_correction  = meta_corr.get("name_correction")
            has_meta_flags   = bool(meta_issues or date_correction or name_correction)

            total_items = len(flagged) + (1 if date_correction else 0) + (1 if name_correction else 0) + len(meta_issues)

            if total_items == 0 and flagged.empty:
                delete_pending_review(pid, report_date)
                continue

            with st.expander(
                f"📋 {patient_name} · {report_date} · {total_items} item(s) to review",
                expanded=True
            ):
                accepted_tests = []
                rejected_tests = []
                apply_date     = False
                reject_date    = False
                apply_name     = False
                reject_name    = False

                # ── SECTION 1: METADATA FLAGS ─────────────────────────────
                if has_meta_flags:
                    st.markdown('<div class="section-label">📋 Metadata Issues</div>',
                                unsafe_allow_html=True)

                    # Generic metadata issues (no accept/reject needed — informational)
                    for issue in meta_issues:
                        st.warning(f"📋 {issue}")

                    # Date correction
                    if date_correction:
                        col_i, col_a, col_r = st.columns([5, 1, 1])
                        with col_i:
                            src = meta_corr.get("date_source", "report text")
                            st.markdown("📋 **DATE CORRECTION**", unsafe_allow_html=True)
                            st.caption(
                                f"Regex missed the date. Claude read **{date_correction}** "
                                f"from '{src}'. Current stored date: "
                                f"**{report_date or '(empty)'}**"
                            )
                        with col_a:
                            if st.button("✓ Accept", key=f"acc_date_{pid}_{report_date}", type="primary"):
                                apply_date = True
                        with col_r:
                            if st.button("✗ Reject", key=f"rej_date_{pid}_{report_date}"):
                                reject_date = True

                    # Name correction
                    if name_correction:
                        col_i, col_a, col_r = st.columns([5, 1, 1])
                        with col_i:
                            regex_name = history["patient_name"].iloc[0] if not history.empty else "?"
                            st.markdown("📋 **NAME CORRECTION**", unsafe_allow_html=True)
                            st.caption(
                                f"Stored name: **{regex_name}** → "
                                f"Claude read: **{name_correction}**"
                            )
                        with col_a:
                            if st.button("✓ Accept", key=f"acc_name_{pid}_{report_date}", type="primary"):
                                apply_name = True
                        with col_r:
                            if st.button("✗ Reject", key=f"rej_name_{pid}_{report_date}"):
                                reject_name = True

                # ── SECTION 2: VALUE / UNIT / RANGE FLAGS ─────────────────
                if not flagged.empty:
                    st.markdown('<div class="section-label" style="margin-top:1.2rem">'
                                'Value &amp; Range Checks</div>', unsafe_allow_html=True)

                    for _, row in flagged.iterrows():
                        test     = row["test_name"]
                        status   = row["status"]
                        conf     = row.get("confidence", "high")
                        note     = row.get("note", "")
                        r_val    = row["regex_value"]
                        r_unit   = row.get("regex_unit", "")
                        llm_val  = row["llm_value"]
                        llm_unit = row.get("llm_unit", "")
                        rflag    = row.get("range_flag", "")
                        rnote    = row.get("range_note", "")
                        unote    = row.get("unit_note", "")

                        # Build badge + description
                        if status == "missed_by_regex":
                            badge = "🆕 **MISSED**"
                            desc  = f"Not extracted by regex. Claude found: **{llm_val} {llm_unit}**"
                        elif status == "corrected":
                            badge = "⚠️ **CORRECTED**"
                            desc  = f"Regex: **{r_val} {r_unit}** → Claude: **{llm_val} {llm_unit}**"
                            if unote:
                                desc += f" _(unit: {unote})_"
                        else:
                            badge = "❓ **LOW CONFIDENCE**"
                            desc  = f"Regex: **{r_val} {r_unit}** — Claude unsure"

                        # Range badge (informational — shown even when value is kept as-is)
                        range_badge = ""
                        if rflag == "CRITICAL_HIGH":
                            range_badge = " 🔴 **CRITICAL HIGH**"
                        elif rflag == "CRITICAL_LOW":
                            range_badge = " 🔴 **CRITICAL LOW**"
                        elif rflag == "HIGH":
                            range_badge = " 📊 **HIGH**"
                        elif rflag == "LOW":
                            range_badge = " 📊 **LOW**"

                        col_info, col_accept, col_reject = st.columns([5, 1, 1])
                        with col_info:
                            st.markdown(
                                f"{badge}{range_badge} &nbsp; **{test}**",
                                unsafe_allow_html=True
                            )
                            caption_parts = [desc]
                            if rnote:
                                caption_parts.append(f"Range: _{rnote}_")
                            if note:
                                caption_parts.append(f"Note: _{note}_")
                            if conf == "low":
                                caption_parts.append("⚠️ Claude has low confidence")
                            st.caption("  \n".join(caption_parts))

                        widget_key = f"review_{pid}_{report_date}_{test}"
                        with col_accept:
                            if st.button("✓ Accept", key=f"acc_{widget_key}", type="primary"):
                                accepted_tests.append(test)
                        with col_reject:
                            if st.button("✗ Reject", key=f"rej_{widget_key}"):
                                rejected_tests.append(test)

                    # Bulk actions
                    st.markdown("---")
                    col_all, col_none, _ = st.columns([1.5, 1.5, 5])
                    with col_all:
                        if st.button("✓ Accept All", key=f"acc_all_{pid}_{report_date}"):
                            accepted_tests = flagged["test_name"].tolist()
                    with col_none:
                        if st.button("✗ Reject All", key=f"rej_all_{pid}_{report_date}"):
                            rejected_tests = flagged["test_name"].tolist()

                # ── APPLY DECISIONS ────────────────────────────────────────
                any_decision = (accepted_tests or rejected_tests or
                                apply_date or reject_date or
                                apply_name or reject_name)

                if any_decision:
                    current_history = load_history(pid)
                    report_df = current_history[
                        current_history["report_date"].dt.strftime("%Y-%m-%d") == report_date
                    ].copy()

                    # Build effective meta corrections based on user decisions
                    effective_meta = {}
                    if apply_date and date_correction:
                        effective_meta["date_correction"] = date_correction
                    if apply_name and name_correction:
                        effective_meta["name_correction"] = name_correction

                    if not report_df.empty and (accepted_tests or effective_meta):
                        corrected_df = apply_corrections(
                            report_df, diff, accepted_tests,
                            meta_corrections=effective_meta if effective_meta else None
                        )
                        other_dates = current_history[
                            current_history["report_date"].dt.strftime("%Y-%m-%d") != report_date
                        ]
                        full_df = pd.concat([other_dates, corrected_df], ignore_index=True)
                        (STORE_DIR / f"{pid}.csv").write_text(full_df.to_csv(index=False))

                        msgs = []
                        if accepted_tests:
                            msgs.append(f"{len(accepted_tests)} value correction(s)")
                        if effective_meta.get("date_correction"):
                            msgs.append(f"date → {effective_meta['date_correction']}")
                        if effective_meta.get("name_correction"):
                            msgs.append(f"name → {effective_meta['name_correction']}")
                        st.success(f"✓ Applied: {', '.join(msgs)}")

                    if rejected_tests:
                        st.info(f"Rejected {len(rejected_tests)} suggestion(s) — original values kept.")
                    if reject_date:
                        st.info("Date correction rejected — original date kept.")
                    if reject_name:
                        st.info("Name correction rejected — original name kept.")

                    # Check if everything is resolved
                    remaining_tests = [t for t in flagged["test_name"]
                                       if t not in accepted_tests and t not in rejected_tests]
                    date_resolved  = apply_date or reject_date or not date_correction
                    name_resolved  = apply_name or reject_name or not name_correction
                    if not remaining_tests and date_resolved and name_resolved:
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
            The <strong style="color:#fff">Longitudinal Biomarker Intelligence Platform</strong>
            extracts structured data from PDF lab reports, flags out-of-range results,
            and tracks trends across multiple reports over time.
        </p>
        <div class="section-label" style="margin-top:2rem">How It Works</div>
        <p style="color:#d4dbe8;line-height:1.8;font-size:0.88rem">
            1. Upload PDF lab reports — patient identity is detected automatically.<br>
            2. Biomarkers are matched against a dictionary with 200+ canonical names.<br>
            3. Values are compared to sex-specific normal ranges and flagged.<br>
            4. Across multiple reports, trends, charts, and callouts are generated.<br>
            5. Duplicate uploads are detected by file hash and skipped.<br>
            6. Claude (LLM) verifies extracted values and flags errors for review.
        </p>
        <div class="section-label" style="margin-top:2rem">Privacy Notice</div>
        <p style="color:#d4dbe8;line-height:1.8;font-size:0.88rem">
            Reports are processed locally. Patient profiles are stored as CSV files in
            <code style="color:var(--accent)">data/patient_profiles/</code>.
            Do not commit this directory to a public repository.
        </p>
    </div>""", unsafe_allow_html=True)