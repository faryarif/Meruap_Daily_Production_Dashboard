"""
ETL Upload Page — Daily Production Data
-----------------------------------------
Place this file in a folder named 'pages/' next to your main dashboard file.
Streamlit will automatically add it as a second page in the sidebar nav.

Repo structure:
    your-repo/
    ├── streamlit_app.py        ← main dashboard
    ├── requirements.txt
    └── pages/
        └── 1_ETL_Upload.py    ← this file
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from supabase import create_client

# ----------------------------------------------------------------------------
# PAGE CONFIG
# ----------------------------------------------------------------------------
st.set_page_config(page_title="ETL Upload", page_icon="📥", layout="wide")

STATUS_COLORS = {
    "Oil", "Water Source", "Injector", "Gas",
    "Shut-in", "Down", "Plug Abandon",
}

DATA_COLS = ["date", "well_name", "status", "bfpd", "bopd", "injection_rate", "last_test_date"]

# ----------------------------------------------------------------------------
# STYLING
# ----------------------------------------------------------------------------
st.markdown("""
<style>
.stApp { background-color: #0b1220; color: #e2e8f0; }
section[data-testid="stSidebar"] { background-color: #0f1729; }
h1, h2, h3 { color: #e2e8f0 !important; }
.block-container { padding-top: 1.5rem; }
[data-testid="stToolbar"] { display: none; }
[data-testid="stDecoration"] { display: none; }
header[data-testid="stHeader"] { display: none; }
[data-testid="stMetric"] { background-color: #141d2e; border: 1px solid #263144; border-radius: 10px; padding: 14px 16px; }
[data-testid="stMetricLabel"] { color: #64748b; }
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------------------------
# SUPABASE CONNECTION
# ----------------------------------------------------------------------------
@st.cache_resource
def get_supabase():
    return create_client(
        st.secrets["supabase"]["url"].rstrip("/"),
        st.secrets["supabase"]["key"],
    )

def get_existing_dates():
    try:
        resp = get_supabase().table("well_data").select("date").execute()
        return set(r["date"] for r in resp.data) if resp.data else set()
    except Exception:
        return set()

def write_well_data(df: pd.DataFrame):
    client = get_supabase()
    rows = df.to_dict(orient="records")
    clean = []
    for row in rows:
        clean.append({
            k: (None if (isinstance(v, float) and np.isnan(v))
                else str(v) if isinstance(v, pd.Timestamp) else v)
            for k, v in row.items()
        })
    client.table("well_data").insert(clean).execute()

def delete_date(date_str: str):
    get_supabase().table("well_data").delete().eq("date", date_str).execute()

# ----------------------------------------------------------------------------
# VALIDATE
# ----------------------------------------------------------------------------
def validate(df: pd.DataFrame):
    errors, warnings = [], []
    required = set(DATA_COLS)
    missing = required - set(df.columns)
    if missing:
        errors.append(f"Missing columns: {', '.join(sorted(missing))}")
        return errors, warnings
    if df["well_name"].isna().any() or (df["well_name"].astype(str).str.strip() == "").any():
        errors.append("Some rows have an empty well_name")
    if df["date"].isna().any():
        errors.append("Some rows have an empty or unparseable date")
    if (pd.to_numeric(df["bopd"], errors="coerce") < 0).any():
        errors.append("BOPD contains negative values")
    if (pd.to_numeric(df["bfpd"], errors="coerce") < 0).any():
        errors.append("BFPD contains negative values")
    bad_status = set(df["status"].dropna().unique()) - STATUS_COLORS
    if bad_status:
        errors.append(f"Unrecognized status value(s): {', '.join(sorted(bad_status))}")
    if (pd.to_numeric(df["bfpd"], errors="coerce") < pd.to_numeric(df["bopd"], errors="coerce")).any():
        warnings.append("Some rows have BFPD < BOPD — BWPD will be clamped to 0")
    return errors, warnings

# ----------------------------------------------------------------------------
# PAGE
# ----------------------------------------------------------------------------
st.title("📥 ETL — Daily Production Upload")
st.caption("Drag and drop your daily Excel or CSV file. The data will be validated and appended to Supabase.")

# Connection status
try:
    get_supabase().table("well_data").select("well_name").limit(1).execute()
    st.success("✅ Supabase connected")
except Exception as e:
    st.error(f"❌ Cannot connect to Supabase: {e}")
    st.stop()

st.markdown("---")

# ----------------------------------------------------------------------------
# UPLOAD ZONE
# ----------------------------------------------------------------------------
uploaded = st.file_uploader(
    "Drop your Excel or CSV file here",
    type=["xlsx", "xls", "csv"],
    help="Required columns: date, well_name, status, bfpd, bopd, injection_rate, last_test_date",
)

if not uploaded:
    st.info("Waiting for file upload...")
    with st.expander("📋 Expected file format"):
        st.markdown("Your file must contain these columns (order doesn't matter):")
        st.code(
            "date          → YYYY-MM-DD  e.g. 2026-07-01\n"
            "well_name     → Text        e.g. Hawk-1\n"
            "status        → Text        e.g. Oil / Injector / Shut-in / Down / Gas / Water Source / Plug Abandon\n"
            "bfpd          → Number      Barrel fluid per day\n"
            "bopd          → Number      Barrel oil per day\n"
            "injection_rate→ Number      For Injector/Water Source wells; 0 otherwise\n"
            "last_test_date→ Date        e.g. 2026-06-28",
            language="text"
        )
    st.stop()

# ----------------------------------------------------------------------------
# EXTRACT
# ----------------------------------------------------------------------------
try:
    raw = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)
except Exception as e:
    st.error(f"Could not read file: {e}")
    st.stop()

# ----------------------------------------------------------------------------
# TRANSFORM
# ----------------------------------------------------------------------------
raw.columns = raw.columns.str.strip().str.lower().str.replace(" ", "_")
raw["date"] = pd.to_datetime(raw["date"], errors="coerce").dt.strftime("%Y-%m-%d")
for col in ["bfpd", "bopd", "injection_rate"]:
    if col in raw.columns:
        raw[col] = pd.to_numeric(raw[col], errors="coerce").fillna(0)
raw["bwpd"] = (raw["bfpd"] - raw["bopd"]).clip(lower=0)
raw["water_cut_pct"] = (
    raw["bwpd"] / raw["bfpd"].replace(0, np.nan) * 100
).round(1).fillna(0)

# ----------------------------------------------------------------------------
# SUMMARY STATS
# ----------------------------------------------------------------------------
st.subheader("File Summary")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Rows",    len(raw))
c2.metric("Unique Wells",  raw["well_name"].nunique())
c3.metric("Unique Dates",  raw["date"].nunique())
c4.metric("Date Range",
          f"{raw['date'].min()} → {raw['date'].max()}" if not raw["date"].isna().all() else "N/A")

# ----------------------------------------------------------------------------
# VALIDATE
# ----------------------------------------------------------------------------
st.subheader("Validation")
errors, warnings = validate(raw)

if warnings:
    for w in warnings:
        st.warning(f"⚠️ {w}")

if errors:
    for e in errors:
        st.error(f"❌ {e}")
    st.stop()
else:
    st.success("✅ All validation checks passed")

# ----------------------------------------------------------------------------
# DUPLICATE DATE CHECK
# ----------------------------------------------------------------------------
existing_dates = get_existing_dates()
incoming_dates = set(raw["date"].dropna().unique())
overlap = existing_dates & incoming_dates

if overlap:
    st.subheader("⚠️ Duplicate Date Warning")
    st.warning(
        f"The following date(s) already exist in the database: **{', '.join(sorted(overlap))}**\n\n"
        "Choose an action below:"
    )
    dup_action = st.radio(
        "What would you like to do?",
        ["Skip duplicate dates (only insert new dates)",
         "Replace duplicate dates (delete existing rows then insert)",
         "Append anyway (may create duplicate rows)"],
        index=0,
    )
else:
    dup_action = "Append anyway (may create duplicate rows)"

# ----------------------------------------------------------------------------
# PREVIEW
# ----------------------------------------------------------------------------
st.subheader("Data Preview")
preview_cols = ["date", "well_name", "status", "bfpd", "bopd",
                "bwpd", "water_cut_pct", "injection_rate", "last_test_date"]
st.dataframe(raw[[c for c in preview_cols if c in raw.columns]],
             use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------------
# LOAD
# ----------------------------------------------------------------------------
st.subheader("Load to Supabase")
st.markdown(f"Ready to insert **{len(raw)} rows** into the `well_data` table.")

if st.button("📤 Append to Supabase", type="primary", use_container_width=True):
    try:
        insert_df = raw[DATA_COLS].copy()

        if "Skip" in dup_action and overlap:
            insert_df = insert_df[~insert_df["date"].isin(overlap)]
            st.info(f"Skipping {len(overlap)} duplicate date(s) — inserting {len(insert_df)} rows.")
        elif "Replace" in dup_action and overlap:
            with st.spinner("Deleting existing rows for duplicate dates..."):
                for d in sorted(overlap):
                    delete_date(d)
            st.info(f"Deleted existing rows for: {', '.join(sorted(overlap))}")

        if insert_df.empty:
            st.warning("No new rows to insert after applying duplicate handling.")
        else:
            with st.spinner(f"Inserting {len(insert_df)} rows..."):
                write_well_data(insert_df)
            st.success(f"✅ Successfully appended {len(insert_df)} rows to Supabase!")
            st.balloons()

    except Exception as e:
        st.error(f"❌ Failed to write to Supabase: {e}")
