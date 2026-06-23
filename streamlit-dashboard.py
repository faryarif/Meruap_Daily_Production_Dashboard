"""
Daily Production & Well Map Dashboard — Shared via Google Sheets
------------------------------------------------------------------
Run locally:
    pip install streamlit pandas plotly gspread google-auth

Setup (one-time):
    See the setup steps in chat — you need:
    1. A Google Sheet with two tabs: "current" and "history"
    2. A Google service account with Editor access to that sheet
    3. Streamlit secrets configured with the service account + sheet_id

Daily workflow:
    Upload a CSV/Excel in the sidebar -> it overwrites the "current" tab
    AND appends a snapshot to the "history" tab. Anyone who opens the app
    link sees the same shared data immediately (no upload needed on their end).
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import numpy as np
import gspread
from google.oauth2.service_account import Credentials

# ----------------------------------------------------------------------------
# PAGE CONFIG
# ----------------------------------------------------------------------------
st.set_page_config(page_title="Daily Production Dashboard", page_icon="🛢️", layout="wide")

STATUS_COLORS = {"Producing": "#22c55e", "Shut-in": "#f59e0b", "Down": "#ef4444"}
REQUIRED_COLS = ["well_name", "field", "status", "latitude", "longitude", "bopd", "water_cut_pct", "last_test_date"]
HISTORY_COLS = ["date", "well_name", "field", "status", "bopd", "water_cut_pct"]

# ----------------------------------------------------------------------------
# STYLING
# ----------------------------------------------------------------------------
st.markdown("""
<style>
.stApp { background-color: #0b1220; color: #e2e8f0; }
[data-testid="stMetric"] { background-color: #141d2e; border: 1px solid #263144; border-radius: 10px; padding: 14px 16px; }
[data-testid="stMetricLabel"] { color: #64748b; }
section[data-testid="stSidebar"] { background-color: #0f1729; }
h1, h2, h3 { color: #e2e8f0 !important; }
.block-container { padding-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------------------------
# GOOGLE SHEETS CONNECTION
# ----------------------------------------------------------------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]


@st.cache_resource
def get_gsheet_client():
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    return gspread.authorize(creds)


def get_sheet():
    client = get_gsheet_client()
    return client.open_by_key(st.secrets["sheet"]["sheet_id"])


def read_current():
    sheet = get_sheet()
    ws = sheet.worksheet("current")
    records = ws.get_all_records()
    if not records:
        return None
    df = pd.DataFrame(records)
    for col in ["latitude", "longitude", "bopd", "water_cut_pct"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def read_history():
    sheet = get_sheet()
    ws = sheet.worksheet("history")
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame(columns=HISTORY_COLS)
    df = pd.DataFrame(records)
    for col in ["bopd", "water_cut_pct"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def write_current(df: pd.DataFrame):
    sheet = get_sheet()
    ws = sheet.worksheet("current")
    ws.clear()
    ws.update([df.columns.tolist()] + df.astype(str).values.tolist())


def append_history(df: pd.DataFrame, date_str: str):
    sheet = get_sheet()
    ws = sheet.worksheet("history")
    snapshot = df[["well_name", "field", "status", "bopd", "water_cut_pct"]].copy()
    snapshot.insert(0, "date", date_str)
    existing = ws.get_all_values()
    rows = snapshot.astype(str).values.tolist()
    if not existing:
        ws.update([HISTORY_COLS] + rows)
    else:
        ws.append_rows(rows, value_input_option="RAW")


# ----------------------------------------------------------------------------
# SAMPLE DATA (fallback only — used if Sheet is empty and nothing uploaded yet)
# ----------------------------------------------------------------------------
@st.cache_data
def generate_sample_wells():
    rng = np.random.default_rng(42)
    names = ["Hawk-1", "Hawk-2", "Falcon-3", "Falcon-4", "Condor-5", "Condor-6",
              "Osprey-7", "Osprey-8", "Eagle-9", "Eagle-10", "Heron-11", "Heron-12"]
    fields = ["North Block", "South Block", "East Flank"]
    rows = []
    for i, name in enumerate(names):
        base_rate = rng.integers(80, 500)
        roll = rng.random()
        status = "Down" if roll > 0.85 else "Shut-in" if roll > 0.75 else "Producing"
        rows.append({
            "well_name": name, "field": fields[i % 3], "status": status,
            "latitude": -2.5 + (i % 4) * 0.04 + rng.random() * 0.01,
            "longitude": 110.5 + (i // 4) * 0.05 + rng.random() * 0.01,
            "bopd": int(base_rate) if status == "Producing" else 0,
            "water_cut_pct": int(rng.integers(10, 60)),
            "last_test_date": "2026-06-23",
        })
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# SIDEBAR — UPLOAD (writes to shared Google Sheet)
# ----------------------------------------------------------------------------
st.sidebar.title("🛢️ Data Input")
st.sidebar.markdown("Upload today's well data — this updates the **shared dashboard** for everyone.")

uploaded_file = st.sidebar.file_uploader(
    "Upload daily well file", type=["csv", "xlsx", "xls"],
    help="Required columns: " + ", ".join(REQUIRED_COLS),
)

snapshot_date = st.sidebar.date_input("Snapshot date", value=datetime(2026, 6, 23))

if uploaded_file is not None:
    new_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
    missing = set(REQUIRED_COLS) - set(new_df.columns)
    if missing:
        st.sidebar.error(f"Missing required columns: {missing}")
    else:
        if st.sidebar.button("📤 Publish to shared dashboard", type="primary"):
            try:
                write_current(new_df[REQUIRED_COLS])
                append_history(new_df, snapshot_date.strftime("%Y-%m-%d"))
                st.cache_data.clear()
                st.sidebar.success("Published! Everyone with the link now sees this data.")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Couldn't write to Google Sheet: {e}")

st.sidebar.markdown("---")
with st.sidebar.expander("📋 Expected CSV format"):
    st.code(
        "well_name,field,status,latitude,longitude,bopd,water_cut_pct,last_test_date\n"
        "Hawk-1,North Block,Producing,-2.51,110.52,320,22,2026-06-22",
        language="csv",
    )

# ----------------------------------------------------------------------------
# LOAD SHARED DATA (everyone who opens the app sees this)
# ----------------------------------------------------------------------------
try:
    wells_df = read_current()
    history_df = read_history()
    sheet_connected = True
except Exception as e:
    st.error(f"Couldn't connect to Google Sheet — check your secrets configuration. Details: {e}")
    wells_df = None
    history_df = pd.DataFrame(columns=HISTORY_COLS)
    sheet_connected = False

using_sample = wells_df is None or wells_df.empty
if using_sample:
    wells_df = generate_sample_wells()
    if sheet_connected:
        st.info("No data published yet — showing sample data. Upload a file in the sidebar and click 'Publish' to replace it for everyone.")

for col in ["water_cut_pct", "last_test_date"]:
    if col not in wells_df.columns:
        wells_df[col] = "N/A"

# ----------------------------------------------------------------------------
# HEADER
# ----------------------------------------------------------------------------
col_title, col_filter = st.columns([3, 1])
with col_title:
    st.title("Daily Production Dashboard")
    st.caption("All units in BOPD (barrels of oil per day) · Shared live dashboard · " + datetime.now().strftime("%A, %B %d, %Y"))
with col_filter:
    field_options = ["All"] + sorted(wells_df["field"].unique().tolist())
    field_filter = st.selectbox("Field", field_options)

filtered = wells_df if field_filter == "All" else wells_df[wells_df["field"] == field_filter]

# ----------------------------------------------------------------------------
# SUMMARY METRICS
# ----------------------------------------------------------------------------
total_bopd = int(filtered["bopd"].sum())
active_count = int((filtered["status"] == "Producing").sum())
shutin_count = int((filtered["status"] == "Shut-in").sum())
down_count = int((filtered["status"] == "Down").sum())

agg_history = history_df.groupby("date")["bopd"].sum().reset_index().sort_values("date") if not history_df.empty else pd.DataFrame(columns=["date", "bopd"])

pct_change = None
if len(agg_history) >= 2:
    prev, curr = agg_history["bopd"].iloc[-2], agg_history["bopd"].iloc[-1]
    if prev:
        pct_change = round((curr - prev) / prev * 100, 1)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Production", f"{total_bopd:,} BOPD", f"{pct_change:+.1f}% vs yesterday" if pct_change is not None else None)
c2.metric("Producing Wells", f"{active_count} / {len(filtered)}")
c3.metric("Shut-in", shutin_count)
c4.metric("Down", down_count)

st.markdown("")

# ----------------------------------------------------------------------------
# MAP + STATUS BREAKDOWN
# ----------------------------------------------------------------------------
map_col, pie_col = st.columns([1.3, 1])

with map_col:
    st.subheader("Well Map")
    fig_map = px.scatter_map(
        filtered, lat="latitude", lon="longitude", color="status",
        color_discrete_map=STATUS_COLORS, size=[18] * len(filtered), size_max=14,
        hover_name="well_name",
        hover_data={"field": True, "bopd": True, "water_cut_pct": True, "latitude": False, "longitude": False},
        text="well_name", map_style="open-street-map",
    )
    fig_map.update_traces(textposition="top center", textfont=dict(color="black", size=10))
    fig_map.update_layout(
        height=420, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="#0b1220",
        legend=dict(bgcolor="rgba(20,29,46,0.8)", font=dict(color="#e2e8f0")),
        map=dict(
            style="white-bg",
            layers=[{
                "below": "traces", "sourcetype": "raster",
                "sourceattribution": "Esri, Maxar, Earthstar Geographics",
                "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
            }],
        ),
    )
    fig_map.update_maps(bounds=dict(
        west=filtered["longitude"].min() - 0.01, east=filtered["longitude"].max() + 0.01,
        south=filtered["latitude"].min() - 0.01, north=filtered["latitude"].max() + 0.01,
    ))
    st.plotly_chart(fig_map, use_container_width=True)
    st.caption("Basemap: Esri World Imagery (free satellite, no API key).")

with pie_col:
    st.subheader("Status & Field Totals")
    status_counts = filtered["status"].value_counts().reset_index()
    status_counts.columns = ["status", "count"]
    fig_pie = px.pie(status_counts, names="status", values="count", color="status", color_discrete_map=STATUS_COLORS, hole=0.55)
    fig_pie.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
                           legend=dict(font=dict(color="#e2e8f0"), orientation="h"), font=dict(color="#e2e8f0"))
    st.plotly_chart(fig_pie, use_container_width=True)

    field_totals = wells_df.groupby("field")["bopd"].sum().reset_index()
    fig_field = px.bar(field_totals, x="bopd", y="field", orientation="h", color_discrete_sequence=["#38bdf8"])
    fig_field.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
                             font=dict(color="#94a3b8"), xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig_field, use_container_width=True)

# ----------------------------------------------------------------------------
# PRODUCTION TREND (real accumulated history)
# ----------------------------------------------------------------------------
st.subheader("Total Production Trend")
if agg_history.empty:
    st.caption("No history yet — once you publish a few days of data, the trend will appear here.")
else:
    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(
        x=agg_history["date"], y=agg_history["bopd"], mode="lines", fill="tozeroy",
        line=dict(color="#38bdf8", width=2), fillcolor="rgba(56,189,248,0.25)",
    ))
    fig_trend.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
                             font=dict(color="#94a3b8"), xaxis=dict(gridcolor="#263144"), yaxis=dict(gridcolor="#263144", title="BOPD"))
    st.plotly_chart(fig_trend, use_container_width=True)

# ----------------------------------------------------------------------------
# TOP PRODUCERS + REAL WELL DECLINE TREND
# ----------------------------------------------------------------------------
top_col, detail_col = st.columns(2)

with top_col:
    st.subheader("Top Producing Wells")
    top_wells = filtered.sort_values("bopd", ascending=False).head(8)
    fig_top = px.bar(top_wells, x="well_name", y="bopd", color_discrete_sequence=["#38bdf8"])
    fig_top.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
                           font=dict(color="#94a3b8"), xaxis_title=None, yaxis_title="BOPD")
    st.plotly_chart(fig_top, use_container_width=True)

with detail_col:
    st.subheader("Well Decline Trend (real history)")
    selected_well = st.selectbox("Select a well", filtered["well_name"].tolist())
    well_history = history_df[history_df["well_name"] == selected_well].sort_values("date") if not history_df.empty else pd.DataFrame()
    if well_history.empty:
        st.caption(f"No history yet for {selected_well} — publish data over multiple days to build this chart.")
    else:
        fig_decline = px.line(well_history, x="date", y="bopd")
        fig_decline.update_traces(line=dict(color="#f59e0b", width=2))
        fig_decline.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
                                   font=dict(color="#94a3b8"), xaxis=dict(gridcolor="#263144"), yaxis=dict(gridcolor="#263144", title="BOPD"))
        st.plotly_chart(fig_decline, use_container_width=True)

# ----------------------------------------------------------------------------
# WELL TABLE
# ----------------------------------------------------------------------------
st.subheader("Well List")
display_df = filtered[["well_name", "field", "status", "bopd", "water_cut_pct", "last_test_date"]].rename(
    columns={"well_name": "Well", "field": "Field", "status": "Status", "bopd": "BOPD",
             "water_cut_pct": "Water Cut (%)", "last_test_date": "Last Test"}
)
st.dataframe(display_df, use_container_width=True, hide_index=True)

if using_sample:
    st.caption("⚠️ Currently showing sample data — upload + publish a file in the sidebar to share real data with everyone.")
else:
    st.caption("✅ Showing live shared data from Google Sheets.")