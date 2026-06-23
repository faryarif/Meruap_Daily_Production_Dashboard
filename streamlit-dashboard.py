"""
Daily Production & Well Map Dashboard
--------------------------------------
Run locally:
    pip install streamlit pandas plotly
    streamlit run streamlit_app.py

Deploy free:
    1. Push this file (+ requirements.txt) to a GitHub repo
    2. Go to https://share.streamlit.io -> New app -> pick the repo
    3. Done — you get a shareable URL

Daily workflow:
    Just upload a new CSV/Excel export each day in the sidebar.
    No code changes needed.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np

# ----------------------------------------------------------------------------
# PAGE CONFIG
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="Daily Production Dashboard",
    page_icon="🛢️",
    layout="wide",
)

STATUS_COLORS = {"Producing": "#22c55e", "Shut-in": "#f59e0b", "Down": "#ef4444"}

# ----------------------------------------------------------------------------
# DARK THEME STYLING
# ----------------------------------------------------------------------------
st.markdown("""
<style>
.stApp { background-color: #0b1220; color: #e2e8f0; }
[data-testid="stMetric"] {
    background-color: #141d2e;
    border: 1px solid #263144;
    border-radius: 10px;
    padding: 14px 16px;
}
[data-testid="stMetricLabel"] { color: #64748b; }
section[data-testid="stSidebar"] { background-color: #0f1729; }
h1, h2, h3 { color: #e2e8f0 !important; }
.block-container { padding-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------------------------
# SAMPLE DATA GENERATOR (used only if no file is uploaded yet)
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
            "well_name": name,
            "field": fields[i % 3],
            "status": status,
            "latitude": -2.5 + (i % 4) * 0.04 + rng.random() * 0.01,
            "longitude": 110.5 + (i // 4) * 0.05 + rng.random() * 0.01,
            "bopd": int(base_rate) if status == "Producing" else 0,
            "water_cut_pct": int(rng.integers(10, 60)),
            "last_test_date": (datetime(2026, 6, 23) - timedelta(days=int(rng.integers(0, 5)))).strftime("%Y-%m-%d"),
        })
    return pd.DataFrame(rows)


@st.cache_data
def generate_sample_history(wells_df):
    days = 14
    today = datetime(2026, 6, 23)
    records = []
    rng = np.random.default_rng(7)
    for idx in range(days):
        d = today - timedelta(days=days - 1 - idx)
        total = 0
        for _, w in wells_df.iterrows():
            if w["status"] == "Producing":
                decline = 1 - idx * 0.004
                noise = 0.9 + rng.random() * 0.2
                total += w["bopd"] * decline * noise
        records.append({"date": d.strftime("%Y-%m-%d"), "bopd": round(total)})
    return pd.DataFrame(records)


# ----------------------------------------------------------------------------
# SIDEBAR — DATA UPLOAD
# ----------------------------------------------------------------------------
st.sidebar.title("🛢️ Data Input")
st.sidebar.markdown("Upload today's well data (CSV or Excel).")

uploaded_file = st.sidebar.file_uploader(
    "Upload daily well file",
    type=["csv", "xlsx", "xls"],
    help="Required columns: well_name, field, status, latitude, longitude, bopd, water_cut_pct, last_test_date",
)

st.sidebar.markdown("---")
st.sidebar.markdown("**Optional: production history file**")
uploaded_history = st.sidebar.file_uploader(
    "Upload production history (for trend chart)",
    type=["csv", "xlsx", "xls"],
    help="Required columns: date, bopd",
)

st.sidebar.markdown("---")
with st.sidebar.expander("📋 Expected CSV format"):
    st.code(
        "well_name,field,status,latitude,longitude,bopd,water_cut_pct,last_test_date\n"
        "Hawk-1,North Block,Producing,-2.51,110.52,320,22,2026-06-22",
        language="csv",
    )

# ----------------------------------------------------------------------------
# LOAD DATA
# ----------------------------------------------------------------------------
def load_uploaded(file):
    if file is None:
        return None
    if file.name.endswith(".csv"):
        return pd.read_csv(file)
    return pd.read_excel(file)


wells_df = load_uploaded(uploaded_file)
history_df = load_uploaded(uploaded_history)

using_sample = wells_df is None
if using_sample:
    wells_df = generate_sample_wells()
    st.sidebar.info("Showing sample data — upload a file to replace it.")

if history_df is None:
    history_df = generate_sample_history(wells_df)

# Basic column safety checks
required_cols = {"well_name", "field", "status", "latitude", "longitude", "bopd"}
missing = required_cols - set(wells_df.columns)
if missing:
    st.error(f"Uploaded file is missing required columns: {missing}")
    st.stop()

for col in ["water_cut_pct", "last_test_date"]:
    if col not in wells_df.columns:
        wells_df[col] = "N/A"

# ----------------------------------------------------------------------------
# HEADER
# ----------------------------------------------------------------------------
col_title, col_filter = st.columns([3, 1])
with col_title:
    st.title("Daily Production Dashboard")
    st.caption("All units in BOPD (barrels of oil per day) · " + datetime.now().strftime("%A, %B %d, %Y"))
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

# pct change vs previous day in history (if available)
pct_change = None
if len(history_df) >= 2:
    prev = history_df["bopd"].iloc[-2]
    curr = history_df["bopd"].iloc[-1]
    if prev:
        pct_change = round((curr - prev) / prev * 100, 1)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Production", f"{total_bopd:,} BOPD",
          f"{pct_change:+.1f}% vs yesterday" if pct_change is not None else None)
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
        filtered,
        lat="latitude",
        lon="longitude",
        color="status",
        color_discrete_map=STATUS_COLORS,
        size=[18] * len(filtered),
        size_max=14,
        hover_name="well_name",
        hover_data={"field": True, "bopd": True, "water_cut_pct": True, "latitude": False, "longitude": False},
        zoom=10,
        text="well_name",
        map_style="open-street-map",
    )
    fig_map.update_traces(textposition="top center", textfont=dict(color="black", size=10))
    fig_map.update_layout(
        height=420,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="#0b1220",
        legend=dict(bgcolor="rgba(20,29,46,0.8)", font=dict(color="#e2e8f0")),
    )
    st.plotly_chart(fig_map, use_container_width=True)
    st.caption("Basemap: OpenStreetMap (no API key needed). Swap map_style to 'satellite' if you add a Mapbox token.")

with pie_col:
    st.subheader("Status & Field Totals")
    status_counts = filtered["status"].value_counts().reset_index()
    status_counts.columns = ["status", "count"]
    fig_pie = px.pie(
        status_counts, names="status", values="count",
        color="status", color_discrete_map=STATUS_COLORS, hole=0.55,
    )
    fig_pie.update_layout(
        height=200, margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
        legend=dict(font=dict(color="#e2e8f0"), orientation="h"),
        font=dict(color="#e2e8f0"),
    )
    st.plotly_chart(fig_pie, use_container_width=True)

    field_totals = wells_df.groupby("field")["bopd"].sum().reset_index()
    fig_field = px.bar(
        field_totals, x="bopd", y="field", orientation="h",
        color_discrete_sequence=["#38bdf8"],
    )
    fig_field.update_layout(
        height=200, margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
        font=dict(color="#94a3b8"), xaxis_title=None, yaxis_title=None,
    )
    st.plotly_chart(fig_field, use_container_width=True)

# ----------------------------------------------------------------------------
# PRODUCTION TREND
# ----------------------------------------------------------------------------
st.subheader("Total Production Trend")
fig_trend = go.Figure()
fig_trend.add_trace(go.Scatter(
    x=history_df["date"], y=history_df["bopd"],
    mode="lines", fill="tozeroy",
    line=dict(color="#38bdf8", width=2),
    fillcolor="rgba(56,189,248,0.25)",
))
fig_trend.update_layout(
    height=280, margin=dict(l=0, r=0, t=10, b=0),
    paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
    font=dict(color="#94a3b8"),
    xaxis=dict(gridcolor="#263144"), yaxis=dict(gridcolor="#263144", title="BOPD"),
)
st.plotly_chart(fig_trend, use_container_width=True)

# ----------------------------------------------------------------------------
# TOP PRODUCERS + WELL DETAIL
# ----------------------------------------------------------------------------
top_col, detail_col = st.columns(2)

with top_col:
    st.subheader("Top Producing Wells")
    top_wells = filtered.sort_values("bopd", ascending=False).head(8)
    fig_top = px.bar(
        top_wells, x="well_name", y="bopd",
        color_discrete_sequence=["#38bdf8"],
    )
    fig_top.update_layout(
        height=300, margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
        font=dict(color="#94a3b8"), xaxis_title=None, yaxis_title="BOPD",
    )
    st.plotly_chart(fig_top, use_container_width=True)

with detail_col:
    st.subheader("Well Decline Trend")
    selected_well = st.selectbox("Select a well", filtered["well_name"].tolist())
    well_row = filtered[filtered["well_name"] == selected_well].iloc[0]
    base = well_row["bopd"] if well_row["bopd"] > 0 else 200
    decline_df = pd.DataFrame({
        "date": history_df["date"],
        "bopd": [round(base * (1 - i * 0.006) * (0.9 + 0.05 * np.sin(i))) for i in range(len(history_df))],
    })
    fig_decline = px.line(decline_df, x="date", y="bopd", markers=False)
    fig_decline.update_traces(line=dict(color="#f59e0b", width=2))
    fig_decline.update_layout(
        height=300, margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
        font=dict(color="#94a3b8"),
        xaxis=dict(gridcolor="#263144"), yaxis=dict(gridcolor="#263144", title="BOPD"),
    )
    st.plotly_chart(fig_decline, use_container_width=True)

# ----------------------------------------------------------------------------
# WELL TABLE
# ----------------------------------------------------------------------------
st.subheader("Well List")
display_df = filtered[["well_name", "field", "status", "bopd", "water_cut_pct", "last_test_date"]].rename(
    columns={
        "well_name": "Well", "field": "Field", "status": "Status",
        "bopd": "BOPD", "water_cut_pct": "Water Cut (%)", "last_test_date": "Last Test",
    }
)
st.dataframe(display_df, use_container_width=True, hide_index=True)

st.caption("💡 Tip: re-upload a new CSV/Excel file in the sidebar each day to refresh this whole dashboard.")
