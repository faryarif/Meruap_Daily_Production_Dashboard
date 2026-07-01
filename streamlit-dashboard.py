"""
Daily Production & Well Map Dashboard — Shared via Google Sheets
------------------------------------------------------------------
Run locally:
    pip install streamlit pandas plotly gspread google-auth

Google Sheet tabs needed:
    - data      : date, well_name, status, bfpd, bopd, injection_rate, last_test_date
    - locations : well_name, field, latitude, longitude

Daily workflow:
    Append new rows to the 'data' tab with today's date.
    The app auto-treats the latest date as "current" and all rows as history.
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
st.set_page_config(page_title="Meruap Dashboard", page_icon="🛢️", layout="wide")

STATUS_COLORS = {
    "Oil": "#22c55e",
    "Water Source": "#1e3a8a",
    "Injector": "#3b82f6",
    "Gas": "#f97316",
    "Shut-in": "#eab308",
    "Down": "#6b7280",
    "Plug Abandon": "#ef4444",
}

DATA_COLS     = ["date", "well_name", "status", "bfpd", "bopd", "injection_rate", "last_test_date"]
LOCATION_COLS = ["well_name", "field", "latitude", "longitude"]

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
    return get_gsheet_client().open_by_key(st.secrets["sheet"]["sheet_id"])

def read_data():
    ws = get_sheet().worksheet("data")
    records = ws.get_all_records()
    if not records:
        return None, pd.DataFrame(columns=DATA_COLS)
    df = pd.DataFrame(records)
    for col in ["bopd", "bfpd", "injection_rate"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    latest_date = df["date"].max()
    current_df = df[df["date"] == latest_date].drop(columns=["date"]).reset_index(drop=True)
    return current_df, df

def read_locations():
    ws = get_sheet().worksheet("locations")
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame(columns=LOCATION_COLS)
    df = pd.DataFrame(records)
    for col in ["latitude", "longitude"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

# ----------------------------------------------------------------------------
# SAMPLE DATA
# ----------------------------------------------------------------------------
@st.cache_data
def generate_sample_data():
    rng = np.random.default_rng(42)
    names = ["Hawk-1", "Hawk-2", "Falcon-3", "Falcon-4", "Condor-5", "Condor-6",
             "Osprey-7", "Osprey-8", "Eagle-9", "Eagle-10", "Heron-11", "Heron-12"]
    base_rows = []
    for name in names:
        base_rate = rng.integers(80, 500)
        roll = rng.random()
        status = "Down" if roll > 0.85 else "Shut-in" if roll > 0.75 else "Oil"
        bopd_val = int(base_rate) if status == "Oil" else 0
        bfpd_val = int(bopd_val * 1.3) if status == "Oil" else 0
        base_rows.append({
            "well_name": name, "status": status,
            "bfpd": bfpd_val, "bopd": bopd_val,
            "injection_rate": int(base_rate * 0.8) if status in ("Injector", "Water Source") else 0,
            "last_test_date": "2026-06-23",
        })
    current_df = pd.DataFrame(base_rows)
    history_rows = []
    for d in range(14):
        date_str = (datetime(2026, 6, 23) - pd.Timedelta(days=13 - d)).strftime("%Y-%m-%d")
        for row in base_rows:
            history_rows.append({**row, "date": date_str})
    return current_df, pd.DataFrame(history_rows)

@st.cache_data
def generate_sample_locations():
    rng = np.random.default_rng(42)
    names = ["Hawk-1", "Hawk-2", "Falcon-3", "Falcon-4", "Condor-5", "Condor-6",
             "Osprey-7", "Osprey-8", "Eagle-9", "Eagle-10", "Heron-11", "Heron-12"]
    fields = ["North Block", "South Block", "East Flank"]
    return pd.DataFrame([{
        "well_name": name,
        "field": fields[i % 3],
        "latitude": -2.5 + (i % 4) * 0.04 + rng.random() * 0.01,
        "longitude": 110.5 + (i // 4) * 0.05 + rng.random() * 0.01,
    } for i, name in enumerate(names)])

# ----------------------------------------------------------------------------
# LOAD DATA
# ----------------------------------------------------------------------------
try:
    wells_df, history_df = read_data()
    locations_df = read_locations()
    sheet_connected = True
except Exception as e:
    st.error(f"Couldn't connect to Google Sheet — check your secrets configuration. Details: {e}")
    wells_df = None
    history_df = pd.DataFrame(columns=DATA_COLS)
    locations_df = pd.DataFrame(columns=LOCATION_COLS)
    sheet_connected = False

using_sample = wells_df is None or wells_df.empty
if using_sample:
    wells_df, history_df = generate_sample_data()
    locations_df = generate_sample_locations()
    if sheet_connected:
        st.info("No data yet — showing sample data. Add rows to the 'data' tab in your Google Sheet.")

for col in ["injection_rate", "last_test_date"]:
    if col not in wells_df.columns:
        wells_df[col] = "N/A" if col == "last_test_date" else 0

wells_df = wells_df.merge(locations_df, on="well_name", how="left")
wells_df["bwpd"] = (wells_df["bfpd"] - wells_df["bopd"]).clip(lower=0)
wells_df["water_cut_pct"] = (
    wells_df["bwpd"] / wells_df["bfpd"].replace(0, np.nan) * 100
).round(1).fillna(0)

missing_coords = wells_df["latitude"].isna() | wells_df["longitude"].isna()
if missing_coords.any() and not using_sample:
    st.warning(
        "These wells have no saved coordinates yet, so they won't appear on the map: "
        + ", ".join(wells_df.loc[missing_coords, "well_name"].tolist())
        + ". Add them to the 'locations' tab in your Google Sheet."
    )

# ----------------------------------------------------------------------------
# HEADER
# ----------------------------------------------------------------------------
col_title, col_filter = st.columns([4, 1])
with col_title:
    st.title("Daily Production Dashboard")
    st.caption("· Shared live dashboard · " + datetime.now().strftime("%A, %B %d, %Y"))
with col_filter:
    field_options = ["All"] + sorted(wells_df["field"].dropna().unique().tolist())
    field_filter = st.selectbox("Field", field_options)

filtered = wells_df if field_filter == "All" else wells_df[wells_df["field"] == field_filter]

# ----------------------------------------------------------------------------
# SUMMARY METRICS
# ----------------------------------------------------------------------------
total_bopd         = int(filtered["bopd"].sum())
active_count       = int((filtered["status"] == "Oil").sum())
shutin_count       = int((filtered["status"] == "Shut-in").sum())
down_count         = int((filtered["status"] == "Down").sum())
injector_count     = int((filtered["status"] == "Injector").sum())
water_source_count = int((filtered["status"] == "Water Source").sum())
total_injection    = int(filtered.loc[filtered["status"] == "Injector", "injection_rate"].sum())
total_water_source = int(filtered.loc[filtered["status"] == "Water Source", "bwpd"].sum())
total_water_production = int(filtered["bwpd"].sum())

agg_history = (
    history_df.groupby("date")["bopd"].sum().reset_index().sort_values("date")
    if not history_df.empty else pd.DataFrame(columns=["date", "bopd"])
)

bopd_change = None
injection_change = None
water_prod_change = None
water_source_change = None

if len(agg_history) >= 2:
    prev = agg_history["bopd"].iloc[-2]
    curr = agg_history["bopd"].iloc[-1]
    if prev:
        bopd_change = int(curr - prev)

if not history_df.empty:
    dates = sorted(history_df["date"].unique())
    if len(dates) >= 2:
        prev_date, curr_date = dates[-2], dates[-1]
        prev_df = history_df[history_df["date"] == prev_date]
        curr_df = history_df[history_df["date"] == curr_date]

        prev_inj  = int(prev_df.loc[prev_df["status"] == "Injector", "injection_rate"].sum())
        curr_inj  = int(curr_df.loc[curr_df["status"] == "Injector", "injection_rate"].sum())
        injection_change = curr_inj - prev_inj

        # bwpd derived on the fly for history rows
        prev_df = prev_df.copy()
        curr_df = curr_df.copy()
        prev_df["bwpd"] = (prev_df["bfpd"] - prev_df["bopd"]).clip(lower=0)
        curr_df["bwpd"] = (curr_df["bfpd"] - curr_df["bopd"]).clip(lower=0)

        water_prod_change   = int(curr_df["bwpd"].sum()) - int(prev_df["bwpd"].sum())
        water_source_change = (
            int(curr_df.loc[curr_df["status"] == "Water Source", "bwpd"].sum()) -
            int(prev_df.loc[prev_df["status"] == "Water Source", "bwpd"].sum())
        )

row1_c1, row1_c2, row1_c3, row1_c4 = st.columns(4)
row1_c1.metric("Total Production",
               f"{total_bopd:,} BOPD",
               f"{bopd_change:+,} BOPD vs yesterday" if bopd_change is not None else None)
row1_c2.metric("Total Injection",
               f"{total_injection:,} Barrels",
               f"{injection_change:+,} Barrels vs yesterday" if injection_change is not None else None)
row1_c3.metric("Total Water Production",
               f"{total_water_production:,} BWPD",
               f"{water_prod_change:+,} BWPD vs yesterday" if water_prod_change is not None else None)
row1_c4.metric("Total Water Source",
               f"{total_water_source:,} BWPD",
               f"{water_source_change:+,} BWPD vs yesterday" if water_source_change is not None else None)

st.markdown("")

# ----------------------------------------------------------------------------
# STATUS & FIELD TOTALS  +  WELL MAP
# ----------------------------------------------------------------------------
pie_col, map_col = st.columns([1, 1.3])

with pie_col:
    st.subheader("Status & Field Totals")
    status_counts = filtered["status"].value_counts().reset_index()
    status_counts.columns = ["status", "count"]
    fig_pie = px.pie(status_counts, names="status", values="count",
                     color="status", color_discrete_map=STATUS_COLORS, hole=0.55)
    fig_pie.update_traces(
        texttemplate="%{label}: %{value}",
        textposition="outside",
        hovertemplate="%{label}: %{value} wells<extra></extra>",
    )
    fig_pie.update_layout(
        height=200, margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
        legend=dict(font=dict(color="#e2e8f0"), orientation="h"),
        font=dict(color="#e2e8f0"))
    st.plotly_chart(fig_pie, use_container_width=True)

    field_totals = wells_df.groupby("field")["bopd"].sum().reset_index()
    field_order = ["North", "South", "East", "West"]
    field_totals["sort_key"] = field_totals["field"].apply(
        lambda f: next((i for i, k in enumerate(field_order) if k.lower() in f.lower()), len(field_order))
    )
    field_totals = field_totals.sort_values("sort_key").drop(columns="sort_key")
    fig_field = px.bar(field_totals, x="bopd", y="field", orientation="h",
                       color_discrete_sequence=["#38bdf8"])
    fig_field.update_layout(
        height=200, margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
        font=dict(color="#94a3b8"), xaxis_title=None, yaxis_title=None,
        yaxis=dict(categoryorder="array", categoryarray=field_totals["field"].tolist()[::-1]))
    st.plotly_chart(fig_field, use_container_width=True)

with map_col:
    st.subheader("Well Map")
    mappable = filtered.dropna(subset=["latitude", "longitude"])
    fig_map = px.scatter_map(
        mappable, lat="latitude", lon="longitude", color="status",
        color_discrete_map=STATUS_COLORS, size=[18] * len(mappable), size_max=14,
        hover_name="well_name",
        hover_data={"field": True, "bopd": True, "water_cut_pct": True,
                    "latitude": False, "longitude": False},
        text="well_name", map_style="open-street-map",
    )
    fig_map.update_traces(textposition="top center", textfont=dict(color="white", size=11))
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
    if not mappable.empty:
        fig_map.update_maps(bounds=dict(
            west=mappable["longitude"].min() - 0.01, east=mappable["longitude"].max() + 0.01,
            south=mappable["latitude"].min() - 0.01, north=mappable["latitude"].max() + 0.01,
        ))
    st.plotly_chart(fig_map, use_container_width=True)

# ----------------------------------------------------------------------------
# PRODUCTION TREND
# ----------------------------------------------------------------------------
st.subheader("Total Production Trend")
if agg_history.empty:
    st.caption("No history yet — add a few days of data to see the trend.")
else:
    # Build full trend df with bwpd and water_cut_pct derived per date
    trend_df = history_df.copy()
    trend_df["bwpd"] = (trend_df["bfpd"] - trend_df["bopd"]).clip(lower=0)
    trend_df["water_cut_pct"] = (
        trend_df["bwpd"] / trend_df["bfpd"].replace(0, np.nan) * 100
    ).round(1).fillna(0)
    trend_agg = trend_df.groupby("date").agg(
        bfpd=("bfpd", "sum"),
        bopd=("bopd", "sum"),
        bwpd=("bwpd", "sum"),
        water_cut_pct=("water_cut_pct", "mean"),
    ).reset_index().sort_values("date")
    trend_agg["water_cut_pct"] = trend_agg["water_cut_pct"].round(1)

    trend_tab1, trend_tab2, trend_tab3, trend_tab4 = st.tabs(["BOPD", "BFPD", "BWPD", "Water Cut %"])

    def make_trend_fig(y_col, line_color, fill_color, y_title):
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=trend_agg["date"], y=trend_agg[y_col],
            mode="lines", fill="tozeroy",
            line=dict(color=line_color, width=2),
            fillcolor=fill_color,
        ))
        fig.update_layout(
            height=280, margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
            font=dict(color="#94a3b8"),
            xaxis=dict(gridcolor="#263144"),
            yaxis=dict(gridcolor="#263144", title=y_title))
        return fig

    with trend_tab1:
        st.plotly_chart(make_trend_fig("bopd", "#38bdf8", "rgba(56,189,248,0.2)",  "BOPD"), use_container_width=True)
    with trend_tab2:
        st.plotly_chart(make_trend_fig("bfpd", "#22c55e", "rgba(34,197,94,0.2)",   "BFPD"), use_container_width=True)
    with trend_tab3:
        st.plotly_chart(make_trend_fig("bwpd", "#f59e0b", "rgba(245,158,11,0.2)",  "BWPD"), use_container_width=True)
    with trend_tab4:
        fig_wc = go.Figure()
        fig_wc.add_trace(go.Scatter(
            x=trend_agg["date"], y=trend_agg["water_cut_pct"],
            mode="lines+markers",
            line=dict(color="#ef4444", width=2),
            fill="tozeroy", fillcolor="rgba(239,68,68,0.15)",
        ))
        fig_wc.update_layout(
            height=280, margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
            font=dict(color="#94a3b8"),
            xaxis=dict(gridcolor="#263144"),
            yaxis=dict(gridcolor="#263144", title="Water Cut (%)", range=[0, 100]))
        st.plotly_chart(fig_wc, use_container_width=True)

# ----------------------------------------------------------------------------
# INJECTION RATE TREND
# ----------------------------------------------------------------------------
st.subheader("Injection Rate Trend")
if history_df.empty:
    st.caption("No history yet — add a few days of data to see the trend.")
else:
    inj_hist = history_df[history_df["status"].isin(["Injector", "Water Source"])]
    if inj_hist.empty:
        st.caption("No Injector or Water Source wells found in data yet.")
    else:
        inj_by_date = inj_hist.groupby(["date", "status"])["injection_rate"].sum().reset_index().sort_values("date")
        fig_inj = px.line(inj_by_date, x="date", y="injection_rate", color="status",
                          color_discrete_map=STATUS_COLORS, markers=True)
        fig_inj.update_layout(
            height=280, margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
            font=dict(color="#94a3b8"),
            xaxis=dict(gridcolor="#263144"), yaxis=dict(gridcolor="#263144", title="Injection Rate"),
            legend=dict(font=dict(color="#e2e8f0"), orientation="h"))
        st.plotly_chart(fig_inj, use_container_width=True)

# ----------------------------------------------------------------------------
# TOP PRODUCERS  +  WELL DECLINE TREND
# ----------------------------------------------------------------------------
top_col, detail_col = st.columns(2)

with top_col:
    st.subheader("Top Producing Wells")
    top_wells = filtered.sort_values("bopd", ascending=False).head(8)
    fig_top = px.bar(top_wells, x="well_name", y="bopd", color_discrete_sequence=["#38bdf8"])
    fig_top.update_layout(
        height=300, margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
        font=dict(color="#94a3b8"), xaxis_title=None, yaxis_title="BOPD")
    st.plotly_chart(fig_top, use_container_width=True)

with detail_col:
    st.subheader("Well Decline Trend")
    selected_well = st.selectbox("Select a well", filtered["well_name"].tolist())
    well_history = (
        history_df[history_df["well_name"] == selected_well].sort_values("date")
        if not history_df.empty else pd.DataFrame()
    )
    if well_history.empty:
        st.caption(f"No history yet for {selected_well} — add multiple days of data to build this chart.")
    else:
        fig_decline = px.line(well_history, x="date", y="bopd")
        fig_decline.update_traces(line=dict(color="#f59e0b", width=2))
        fig_decline.update_layout(
            height=300, margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
            font=dict(color="#94a3b8"),
            xaxis=dict(gridcolor="#263144"), yaxis=dict(gridcolor="#263144", title="BOPD"))
        st.plotly_chart(fig_decline, use_container_width=True)

# ----------------------------------------------------------------------------
# WELL TABLE
# ----------------------------------------------------------------------------
st.subheader("Well List")
display_df = filtered[["well_name", "field", "status", "bfpd", "bopd", "bwpd",
                        "water_cut_pct", "injection_rate", "last_test_date"]].rename(
    columns={"well_name": "Well", "field": "Field", "status": "Status",
             "bfpd": "BFPD", "bopd": "BOPD", "bwpd": "BWPD",
             "water_cut_pct": "Water Cut (%)", "injection_rate": "Injection Rate",
             "last_test_date": "Last Test"}
)
st.dataframe(display_df, use_container_width=True, hide_index=True)

if using_sample:
    st.caption("⚠️ Showing sample data — add rows to the 'data' tab in your Google Sheet to see real data.")
else:
    st.caption("✅ Showing live shared data from Google Sheets.")
