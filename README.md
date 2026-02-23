# 🧬 Longitudinal Biomarker Intelligence Platform

A Streamlit web app that extracts biomarker data from PDF lab reports, flags out-of-range values, and tracks trends over time across multiple reports.

## Features

- **Auto-extraction** — Pulls biomarker values from PDFs using a 200+ alias dictionary
- **Smart patient ID** — Recognises the same patient across reports from different labs
- **Status flagging** — Compares values against sex-specific normal ranges
- **Longitudinal trends** — Shows % change and direction across visits
- **Export** — Download results as CSV at any stage

## Setup

```bash
pip install -r requirements.txt
```

Place your `Biomarker_dictionary_csv.csv` in the `data/` directory.

## Run locally

```bash
streamlit run app.py
```

## Deploy to Streamlit Cloud

1. Push this repo to GitHub (ensure `data/patient_profiles/` is in `.gitignore`)
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your repo → set main file to `app.py` → Deploy

## File Structure

```
├── app.py                          # Streamlit UI
├── lab_extractor.py                # Extraction + analysis logic
├── requirements.txt
├── .gitignore
└── data/
    ├── Biomarker_dictionary_csv.csv  # Reference dictionary (add this yourself)
    └── patient_profiles/             # Auto-generated, gitignored
```

## Privacy

Patient profiles are stored locally in `data/patient_profiles/`. Never commit this folder to a public repository if reports contain identifiable health data.
