

pip install pdfplumber pandas """ Longitudinal Biomarker Intelligence Platform v4 Robust extraction + longitudinal trends + patient profiles """ import re import hashlib import pdfplumber import pandas as pd from pathlib import Path from datetime import datetime DATA_DIR = Path("/Users/vass/Docu

pasted

i want to make this ipynb to python script, so i can push to github and then as a web app to streamlit. Tell me how to do it

10:02 AM
I can see you already have a Python script here (not a notebook), so the main task is adapting it for Streamlit. Here's the plan:

What you need to do
Step 1: Restructure paths for deployment

Your current code uses hardcoded local paths like /Users/vass/Documents/.... For Streamlit, you need relative paths:

python
BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
REPORTS_DIR = DATA_DIR / "reports"
STORE_DIR  = DATA_DIR / "patient_profiles"
DICT_PATH  = DATA_DIR / "Biomarker_dictionary_csv.csv"
```

**Step 2: Create your repo structure**
```
my-lab-app/
├── app.py                        ← Streamlit UI
├── lab_extractor.py              ← Your existing script (cleaned up)
├── data/
│   ├── Biomarker_dictionary_csv.csv
│   └── patient_profiles/         ← gitkeep this folder
├── requirements.txt
└── .gitignore
```

**Step 3: Create `requirements.txt`**
```
pdfplumber
pandas
streamlit
Step 4: Write app.py

python
import streamlit as st
import tempfile
from pathlib import Path
from lab_extractor import process_pdf, save_report, load_history, generate_trends, print_patient_profile

st.title("🧬 Longitudinal Biomarker Intelligence Platform")

uploaded_files = st.file_uploader("Upload lab report PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    for uploaded_file in uploaded_files:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = Path(tmp.name)

        df = process_pdf(tmp_path, verbose=False)
        if not df.empty:
            save_report(df)
            pid = df["patient_id"].iloc[0]
            history = load_history(pid)
            trends  = generate_trends(history)

            st.subheader(f"Patient: {df['patient_name'].iloc[0]}")
            st.dataframe(df[["test_name", "value", "unit", "status"]])

            if not trends.empty:
                st.subheader("Trends")
                st.dataframe(trends)
        else:
            st.warning(f"No data extracted from {uploaded_file.name}")
Step 5: Push to GitHub

bash
git init
git add .
git commit -m "initial commit"
gh repo create my-lab-app --public --push
```

**Step 6: Deploy to Streamlit Cloud**

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Connect your GitHub account
3. Select your repo, set main file to `app.py`
4. Click **Deploy**

---

## Key things to watch out for

**Privacy/HIPAA**: You're uploading real patient lab reports. Streamlit Cloud stores files temporarily but the `patient_profiles/` CSVs will persist in your repo if you're not careful. Add to `.gitignore`:
```
data/patient_profiles/
data/all_biomarkers.csv
data/reports/
Persistent storage: Streamlit Cloud's filesystem resets on redeploy. If you want profiles to persist across sessions, you'd need to swap STORE_DIR for a database like Supabase or store CSVs in a private S3 bucket.

The print_patient_profile function uses print() — in Streamlit you'll want to replace that with st.write() or st.text() calls, or build a proper UI from the dataframes directly.

Want me to write the full app.py with a polished Streamlit UI?

yes

10:04 AM

Check available skills
Check available skills
Now let me build the full Streamlit app. I'll create both files needed.


Created 6 files, ran a command, read a file
Created 6 files, ran a command, read a file
Here's everything you need. Your repo structure should be:

your-repo/
├── app.py                        ← Streamlit UI (the main file)
├── lab_extractor.py              ← Your extraction logic (cleaned up)
├── requirements.txt
├── .gitignore
├── README.md
└── data/
    ├── Biomarker_dictionary_csv.csv   ← add this manually
    └── patient_profiles/              ← auto-created, gitignored
To go live:

bash
# 1. Set up repo
git init
git add .
git commit -m "initial commit"
gh repo create biomarker-platform --public --push

# 2. Deploy
# Go to share.streamlit.io → New app → select your repo → main file: app.py → Deploy
What the app includes:

Dark clinical UI with status-coloured pills (green/red/yellow) for Normal/HIGH/LOW
Upload page — drag-drop PDFs, processes them immediately, shows results per patient
Patient Profiles page — browse all stored patients, view history across visits
Trends tab — % change with worsening/improving callout banners
CSV export at every level (latest snapshot, trends, full history)
About page with privacy notice
The one thing you need to add manually is your Biomarker_dictionary_csv.csv into the data/ folder before pushing — don't commit data/patient_profiles/ if your reports contain real patient data.

App
PY 
Lab extractor
PY 
Requirements
TXT 
.gitignore
GITIGNORE 
Readme
Document · MD 
2019.pdf
pdf


""" Longitudinal Biomarker Intelligence Platform Streamlit Web App """ import tempfile import io from pathlib import Path import pandas as pd import streamlit as st from lab_extractor import ( process_pdf, save_report, load_history, generate_trends, list_patients, STORE_DIR ) # ─────────

pasted


""" Longitudinal Biomarker Intelligence Platform v4 Robust extraction + longitudinal trends + patient profiles """ import re import hashlib import pdfplumber import pandas as pd from pathlib import Path from datetime import datetime BASE_DIR = Path(__file__).parent DATA_DIR = BASE_DIR / "dat

pasted

here is my latest app.py and logic. When i upload this lab test, its not picking up the sex, name of patients name and trend graphs are not showing.

3:44 PM
Looking at the PDF, I can see the exact issues. Let me diagnose:


Ran 5 commands
Ran 5 commands
Good — found the root cause. The patient line in this lab format has Patient : P0006027 Mr. SRINIWAS SRIRAM (32/M) — the lab's own patient ID sits between Patient : and Mr., which breaks the name/gender regex. Let me fix all the bugs now:


Ran 3 commands
Ran 3 commands
Now I have the full picture. Three distinct bugs:

Name/gender not extracted — Patient : P0006027 Mr. SRINIWAS SRIRAM (32/M) has a lab ID between Patient : and Mr. that breaks the regex
DHEA Sulphate unit on next line — value 425.70 has no unit on its line; unit Microgm/dl is on line+2, not line+1
Trends not showing — this is a downstream effect of bug #1 (no gender → wrong patient ID → can't match across reports)
Let me fix all of these in lab_extractor.py:


Edited 2 files
Edited 2 files
Now let me verify the fix works end-to-end on the actual PDF:


Ran 2 commands
Ran 2 commands
Both fixes work. Now copy the corrected file to outputs:


Ran a command, read a file
Ran a command, read a file
Here are the 3 bugs found and fixed, all in lab_extractor.py:

Bug 1 — Name & gender not extracted (root cause of missing trends too) The Hitech PDF format puts their internal patient ID between the label and the name: Patient : P0006027 Mr. SRINIWAS SRIRAM (32/M). The old regex expected Mr. immediately after Patient : and got no match. Fixed by making that ID token optional in the pattern.

Bug 2 — DHEA Sulphate unit on a separate line DHEA SULPHATE 425.70 appears on one line, with Microgm/dl two lines below it. The old code only checked the next 1 line. Fixed by looking up to 2 lines ahead, and adding a second pass to pick up a standalone unit line when the value was found but unit was empty.

Bug 3 — Trends not showing This was purely downstream of Bug 1 — without name/gender, make_patient_id() fell back to a hash of UNKNOWN|XX, so each upload created a different patient ID and there was never more than one report per "patient" to trend.

Lab extractor
PY 
I need an option to delete previous data.
I need the trends section to show a line chart below the table. Each selected test name should show trend graph
If user uploads same file again, it should not process duplicates
Instead of first value and latest value, please include year tested
4:11 PM
Let me read the current files and implement all 4 changes.


Viewed 2 files
Viewed 2 files
Now I have a complete picture. Let me implement all 4 changes cleanly:

Delete data — in lab_extractor.py + Patient Profiles page
Line charts per selected test — in Trends tab
Duplicate file detection — track source_file hashes before processing
Show dates instead of first/latest labels — in trends table

Created 2 files, ran a command
Created 2 files, ran a command
Now rewrite app.py with all 4 features:


Ran 2 commands, created a file, read a file
Ran 2 commands, created a file, read a file
Here's a summary of every change made:

1. Delete data (Patient Profiles page → 🗑️ Manage / Delete Data expander)

Delete a single report by choosing its date from a dropdown and clicking "Delete this report" — only that date's rows are removed from the CSV
Delete entire patient with "⛔ Delete Patient" — wipes the whole profile file. Both actions call st.rerun() so the UI refreshes immediately
2. Line charts (Trends tab → "Line Charts" section)

A multiselect picker lets you choose which tests to chart (defaults to first 3)
Each selected test gets its own Plotly line chart styled to match the dark theme
Data points are coloured — teal = Normal, red = HIGH, yellow = LOW
Values are labelled directly on the chart; hover shows the full date
3. Duplicate detection (lab_extractor.py → is_duplicate_file())

Every processed PDF now stores its SHA-256 hash in a file_hash column
On upload, the hash is computed before processing and checked against all stored profiles
If matched, upload is skipped with a clear "⏭️ already processed" warning — no re-processing, no duplicate rows
4. Dates instead of first/latest (Trends table)

Columns now show the actual dates: From, Value (From), To, Value (To) instead of the generic "first_value" / "latest_value" labels
Also add plotly to your requirements.txt: pip install pdfplumber pandas streamlit plotly
App
PY 
Lab extractor
PY 

Biomarker Intelligence Logs Feb 23 2026.txt
txt

The line charts are not showing in trends. I am uploading the error log.

4:29 PM
Let me read the log first.


Read the error log
Read the error log
Three clear issues from the log:

plotly not in requirements.txt — the app crashes because plotly is never installed
use_container_width deprecated — Streamlit 1.54 wants width='stretch' instead
Streamlit version unpinned — it installed 1.19.0 first (too old), then resolved to 1.54.0 after fixing, but we should pin it
All three fixes in one go:


Ran 5 commands, viewed a file, read a file
Ran 5 commands, viewed a file, read a file
Three root causes from the log, all now fixed:

1. plotly missing from requirements.txt — this was the crash. Streamlit Cloud installs only what's in that file, and plotly was never listed. Added it.

2. streamlit>=1.54.0 pinned — the log shows Streamlit Cloud first resolved to 1.19.0 (far too old), which then errored on the altair version mismatch. Pinning >=1.54.0 forces the correct modern version from the start.

3. use_container_width=True deprecated — Streamlit 1.54 emits warnings for st.dataframe(..., use_container_width=True) and says to use width='stretch' instead. Fixed in all st.dataframe() calls. Note: st.plotly_chart() still correctly uses use_container_width=True — that deprecation only applies to dataframe/table elements.

Just replace both files in your repo and push — Streamlit Cloud will reinstall with plotly and the charts will render.

Requirements
TXT 
App
PY 
2023.pdf
pdf

The code is not picking up the name from this report. The previous report from 2019 had my full name Sriniwas Sriram, but this one has Sriniwas S.

4:45 PM
Looking at the 2023 PDF, the patient header is completely different from the 2019 format:

2019 (Hitech old): Patient : P0006027 Mr. SRINIWAS SRIRAM (32/M)
2023 (Hitech new): Mr. SRINIWAS S + Age: 36 Year(s) Sex: Male on separate lines
The name SRINIWAS S has only one real word (≥2 chars) — SRINIWAS — so make_patient_id falls to Tier 2 and uses the phone number. Since the 2019 report also has the same phone number (9941555811), it will actually hash to the same patient ID — but let me verify this and also check what the extractor actually sees.


Ran 2 commands
Ran 2 commands
As expected — two different PIDs. The fix needs to be smarter: when the 2023 report has a truncated name (SRINIWAS S) and the 2019 report has the full name (SRINIWAS SRIRAM), the system should recognise them as the same person. The solution is to check first name + phone + gender across existing profiles during save, and merge into the existing record if found.


Ran a command, edited a file
Ran a command, edited a file
Now also add the 2023-format metadata extraction — the new Hitech format has Mr. SRINIWAS S on line 0 with no age/gender, and age/gender on a completely separate line:


Ran 2 commands, edited a file
Ran 2 commands, edited a file
The merge logic is confirmed. Now copy the updated file:


Ran a command, read a file
Ran a command, read a file
Two bugs fixed, only one file changed (lab_extractor.py):

Bug 1 — Name not extracted from 2023 format

The 2023 Hitech report dropped the old Patient : P0006027 Mr. NAME (age/M) layout entirely. It now puts Mr. SRINIWAS S on line 0 followed by Reference: SELF VID: ... on the same line. The old fallback regex looked for \n|Age as the boundary after the name and got no match because Reference appears first. Fixed with a new pattern that accepts Reference or VID as valid terminators.

Bug 2 — 2023 truncated name creates a different patient than 2019 full name

SRINIWAS SRIRAM → Tier 1 hash → P4BB9E87F
SRINIWAS S → Tier 2 hash → PF3C3B7DB ← wrong, creates a second profile

Added _lookup_existing_pid(): before hashing a Tier 2/3 name, it scans existing profiles for one where the stored name's first word matches and gender matches. Since SRINIWAS appears as the first word in the stored SRINIWAS SRIRAM profile, the 2023 report automatically gets routed to P4BB9E87F — the same longitudinal profile — and trends across 2019→2023 will now show correctly.

One thing to note: if you've already uploaded the 2019 report and it created P4BB9E87F, just upload 2023 normally and it will merge. If you uploaded 2023 first (creating a new truncated PID), you'll want to delete that orphan profile and re-upload both in order.

Lab extractor
PY 
I am only picking up these tests from the attached lab report:
test_name
TSH
Testosterone (Total)
Vitamin B12
Vitamin D (25-OH)
value
3
0.252
883
25

The actual tests from the pdf are
Vitamin B12    883
Folic Acid    3.53
Copper    102.6
Vitamin D    34.40
Testosterone    0.252
Free T3    2.61
Free T4    1.03
TSH (hs TSH)    1.750
LH    25.80
FSH    5.98
Prolactin    22.10
Estradiol    232
Progesterone    0.2
Anti-sperm Antibody    11.09

Also, I want the age of the patient to reflect the current age and not the one on the report. So, calculate age based on what the patient age was during testing from the reports and display current age.

Show more
9:23 AM
Let me see the actual PDF to understand the format.


Check what PDF files are available
Check what PDF files are available
Claude's response was interrupted
bev 2021.pdf
pdf

I am only picking up these tests from the attached lab report:
test_name
TSH
Testosterone (Total)
Vitamin B12
Vitamin D (25-OH)
value
3
0.252
883
25

The actual tests from the pdf are
Vitamin B12    883
Folic Acid    3.53
Copper    102.6
Vitamin D    34.40
Testosterone    0.252
Free T3    2.61
Free T4    1.03
TSH (hs TSH)    1.750
LH    25.80
FSH    5.98
Prolactin    22.10
Estradiol    232
Progesterone    0.2
Anti-sperm Antibody    11.09

Also, I want the age of the patient to reflect the current age and not the one on the report. So, calculate age based on what the patient age was during testing from the reports and display current age.

Show more
9:24 AM
Let me debug the extraction precisely against the actual PDF text.


Extract all raw lines from the PDF to see what the extractor sees
Extract all raw lines from the PDF to see what the extractor sees
Now I have the raw text. I can see all the problems clearly. Let me diagnose each failure before writing any code.


Get all lines to diagnose every extraction failure
Get all lines to diagnose every extraction failure
Now I can see every problem precisely. Let me catalog them all before touching any code:


Ran 4 commands
Ran 4 commands
All 13 tests now extract correctly. Now I also need to add miu/ml and mU/100uL to the unit normalizer, fix TSH's unit (µIU/ml isn't captured because of the µ character), and then implement the current age calculation. Let me now write all fixes:


Viewed 2 files
Viewed 2 files
Now I have everything I need. Let me apply all fixes:


Edited 2 files
Edited 2 files
Now fix the unit map to include all units found in this report, and fix find_value_in_text to handle the µIU/ml unit and the mU/100uL unit:


Edited 2 files
Edited 2 files
Also fix the unit lookahead for standalone unit lines to include the new units:


Fix unit lookahead to use expanded unit regex
Fix unit lookahead to use expanded unit regex
Now implement the current age calculation — store birth_year derived from age_at_test and report_date, then display current age in the patient card:


Edited 2 files
Edited 2 files
Now update load_history to expose current age, and update list_patients and render_patient_card in app.py:


Update load_history to compute current_age from birth_year
Update load_history to compute current_age from birth_year
Now update render_patient_card in app.py to show current age:


Update render_patient_card to show current age instead of age at test
Update render_patient_card to show current age instead of age at test
Now verify the full extraction works end-to-end against the real PDF:


End-to-end test of all 13 extractions against real PDF
End-to-end test of all 13 extractions against real PDF
All 14 tests extracted with correct values and units. Now copy to outputs:


Ran a command, read a file
Ran a command, read a file
Here's a precise account of every bug found and fixed:

Missing tests (9 new aliases added)

Test	Root cause
Folic Acid	No alias existed at all
Copper	No alias existed at all
Free T3 / Free T4	No alias existed at all
LH / FSH	No alias existed at all
Prolactin / Estradiol / Progesterone	No alias existed at all
Anti-Sperm Antibody	No alias + mU/100uL unit not recognised
Wrong values on tests that were partially working

TSH reported as 3 — the alias tsh matched at position 0 of TSH 3rd Generation..., then the value regex grabbed 3 from 3rd. Fixed by adding the full alias tsh 3rd generation (hs tsh) which matches the entire test name, so the value search starts after (hs tsh) where 1.750 sits.
Vitamin D reported as 25 — the old aliases 25-oh vitamin d and 25 hydroxy (oh) vit d don't appear in the PDF text. The PDF says VITAMIN D (25-OH). Added vitamin d (25-oh) as the primary alias. Now extracts 34.40 correctly.
Unit recognition gaps — Expanded _UNIT_MAP and the unit regex to cover µIU/mL, mIU/mL, pg/dL, mU/100uL, µg/mL and other units used in endocrinology / serology panels.

Current age — Now stored as birth_year = report_year − age_at_test in every row. load_history() computes datetime.now().year − birth_year at read time, so the patient card always shows age as of today regardless of which report was uploaded.

Lab extractor
PY 
App
PY 





Claude is AI and can make mistakes. Please double-check responses.
App · PY
Copy

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
    delete_patient, delete_report_by_date, STORE_DIR
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

            with st.expander("🗑️  Manage / Delete Data", expanded=False):
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

                st.markdown("---")
                st.markdown('<div class="section-label" style="color:#ff6b6b">Delete entire patient record</div>', unsafe_allow_html=True)
                st.warning(f"This will permanently erase ALL data for **{history['patient_name'].iloc[0]}**.")

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
