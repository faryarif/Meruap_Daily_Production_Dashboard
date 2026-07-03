"""
Daily Production & Well Map Dashboard — Shared via Supabase
------------------------------------------------------------------
Run locally:
    pip install streamlit pandas plotly numpy supabase openpyxl

Supabase tables:
    ProdWellBasiss : Date, UNIQUEID, OIL, GAS, WATER
    HeaderID       : UNIQUEID, ALIAS, field, status, latitude, longitude

Streamlit secrets (.streamlit/secrets.toml):
    [supabase]
    url = "https://xxxx.supabase.co"
    key = "your-anon-public-key"
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import numpy as np
from supabase import create_client

# ----------------------------------------------------------------------------
# PAGE CONFIG
# ----------------------------------------------------------------------------
st.set_page_config(page_title="Meruap Dashboard", page_icon="🛢️", layout="wide",
                   initial_sidebar_state="expanded")

STATUS_COLORS = {
    "Oil": "#22c55e",
    "Water Source": "#1e3a8a",
    "Injector": "#3b82f6",
    "Gas": "#f97316",
    "Shut-in": "#eab308",
    "Down": "#6b7280",
    "Plug Abandon": "#ef4444",
}

PROD_COLS     = ["Date", "UNIQUEID", "OIL", "GAS", "WATER"]
LOCATION_COLS = ["UNIQUEID", "ALIAS", "field", "status", "latitude", "longitude"]

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
[data-testid="stToolbar"] { display: none; }
[data-testid="stDecoration"] { display: none; }
header[data-testid="stHeader"] { display: unset; }
[data-testid="collapsedControl"] { display: unset; }
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

def test_connection():
    try:
        get_supabase().table("ProdWellBasiss").select("UNIQUEID").limit(1).execute()
        return True, "Connected"
    except Exception as e:
        return False, str(e)

# ----------------------------------------------------------------------------
# READ FUNCTIONS
# ----------------------------------------------------------------------------
@st.cache_data(ttl=30, show_spinner=False)
def read_data():
    client = get_supabase()
    resp = client.table("ProdWellBasiss").select(
        "Date, UNIQUEID, OIL, GAS, WATER"
    ).order("Date").execute()
    if not resp.data:
        return None, pd.DataFrame(columns=PROD_COLS)
    df = pd.DataFrame(resp.data)
    for col in ["OIL", "GAS", "WATER"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.rename(columns={"Date": "date"})
    # Derive bfpd = OIL + WATER
    df["bfpd"] = df["OIL"] + df["WATER"]
    # Compute last_test_date per UNIQUEID = latest date that UNIQUEID appears
    last_test = df.groupby("UNIQUEID")["date"].max().reset_index().rename(columns={"date": "last_test_date"})
    df = df.merge(last_test, on="UNIQUEID", how="left")
    latest_date = df["date"].max()
    current_df = df[df["date"] == latest_date].drop(columns=["date"]).reset_index(drop=True)
    return current_df, df

@st.cache_data(ttl=30, show_spinner=False)
def read_locations():
    client = get_supabase()
    resp = client.table("HeaderID").select(
        "UNIQUEID, ALIAS, field, status, latitude, longitude"
    ).execute()
    if not resp.data:
        return pd.DataFrame(columns=LOCATION_COLS)
    df = pd.DataFrame(resp.data)
    for col in ["latitude", "longitude"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

# ----------------------------------------------------------------------------
# SAMPLE DATA
# ----------------------------------------------------------------------------
@st.cache_data
def generate_sample_data():
    rng = np.random.default_rng(42)
    names = [f"W-{i+1:02d}" for i in range(12)]
    base_rows = []
    for name in names:
        base_rate = rng.integers(80, 500)
        oil_val   = int(base_rate)
        water_val = int(oil_val * 0.3)
        gas_val   = int(oil_val * 0.1)
        base_rows.append({
            "UNIQUEID": name,
            "OIL": oil_val, "GAS": gas_val, "WATER": water_val,
            "bfpd": oil_val + water_val,
        })
    history_rows = []
    for d in range(14):
        date_str = (datetime(2026, 6, 23) - pd.Timedelta(days=13 - d)).strftime("%Y-%m-%d")
        for row in base_rows:
            history_rows.append({**row, "date": date_str})
    history_df = pd.DataFrame(history_rows)
    last_test = history_df.groupby("UNIQUEID")["date"].max().reset_index().rename(columns={"date": "last_test_date"})
    history_df = history_df.merge(last_test, on="UNIQUEID", how="left")
    latest_date = history_df["date"].max()
    current_df = history_df[history_df["date"] == latest_date].drop(columns=["date"]).reset_index(drop=True)
    return current_df, history_df

@st.cache_data
def generate_sample_locations():
    rng = np.random.default_rng(42)
    names = [f"W-{i+1:02d}" for i in range(12)]
    fields = ["North Block", "South Block", "East Flank"]
    statuses = ["Oil", "Oil", "Oil", "Shut-in", "Injector", "Water Source",
                "Oil", "Oil", "Down", "Oil", "Gas", "Plug Abandon"]
    return pd.DataFrame([{
        "UNIQUEID": name, "ALIAS": name,
        "field": fields[i % 3], "status": statuses[i],
        "latitude": -2.5 + (i % 4) * 0.04 + rng.random() * 0.01,
        "longitude": 110.5 + (i // 4) * 0.05 + rng.random() * 0.01,
    } for i, name in enumerate(names)])

# ----------------------------------------------------------------------------
# SIDEBAR — CONNECTION STATUS
# ----------------------------------------------------------------------------
with st.sidebar:
    ok, msg = test_connection()
    if ok:
        st.success("✅ Supabase connected")
    else:
        st.error(f"❌ {msg}")

# ----------------------------------------------------------------------------
# LOAD DATA
# ----------------------------------------------------------------------------
try:
    wells_df, history_df = read_data()
    locations_df = read_locations()
    db_connected = True
except Exception as e:
    st.error(f"Couldn't connect to Supabase — check your secrets configuration. Details: {e}")
    wells_df = None
    history_df = pd.DataFrame(columns=PROD_COLS)
    locations_df = pd.DataFrame(columns=LOCATION_COLS)
    db_connected = False

using_sample = wells_df is None or wells_df.empty
if using_sample:
    wells_df, history_df = generate_sample_data()
    locations_df = generate_sample_locations()
    if db_connected:
        st.info("No data yet — showing sample data.")

# Join field, status, ALIAS, coordinates from HeaderID
wells_df = wells_df.merge(locations_df, on="UNIQUEID", how="left")
wells_df["water_cut_pct"] = (
    wells_df["WATER"] / wells_df["bfpd"].replace(0, np.nan) * 100
).round(1).fillna(0)

missing_coords = wells_df["latitude"].isna() | wells_df["longitude"].isna()
if missing_coords.any() and not using_sample:
    st.warning(
        "These wells have no saved coordinates: "
        + ", ".join(wells_df.loc[missing_coords, "UNIQUEID"].tolist())
        + ". Add them to the 'HeaderID' table in Supabase."
    )

# ----------------------------------------------------------------------------
# HEADER
# ----------------------------------------------------------------------------
col_title, col_date, col_filter = st.columns([3, 1, 1])
with col_title:
    st.title("Daily Production Dashboard")
    st.caption("· Shared live dashboard · " + datetime.now().strftime("%A, %B %d, %Y"))
with col_date:
    available_dates = sorted(history_df["date"].unique(), reverse=True) if not history_df.empty else []
    if available_dates:
        available_dates_dt = [datetime.strptime(d, "%Y-%m-%d").date() for d in available_dates]
        selected_date = st.date_input(
            "Snapshot date",
            value=available_dates_dt[0],
            min_value=available_dates_dt[-1],
            max_value=available_dates_dt[0],
        )
        selected_date_str = selected_date.strftime("%Y-%m-%d")
    else:
        selected_date_str = None
with col_filter:
    field_options = ["All"] + sorted(wells_df["field"].dropna().unique().tolist())
    field_filter = st.selectbox("Field", field_options)

# Filter by selected snapshot date
if selected_date_str and not history_df.empty and selected_date_str in history_df["date"].values:
    snap_df = history_df[history_df["date"] == selected_date_str].drop(columns=["date"]).reset_index(drop=True)
    snap_df = snap_df.merge(locations_df, on="UNIQUEID", how="left")
    snap_df["water_cut_pct"] = (
        snap_df["WATER"] / snap_df["bfpd"].replace(0, np.nan) * 100
    ).round(1).fillna(0)
    display_wells = snap_df
else:
    display_wells = wells_df

filtered = display_wells if field_filter == "All" else display_wells[display_wells["field"] == field_filter]

# ----------------------------------------------------------------------------
# SUMMARY METRICS
# ----------------------------------------------------------------------------
total_oil          = int(filtered["OIL"].sum())
total_gas          = int(filtered["GAS"].sum())
total_water        = int(filtered["WATER"].sum())
total_water_source = int(filtered.loc[filtered["status"] == "Water Source", "WATER"].sum())

agg_history = (
    history_df.groupby("date")["OIL"].sum().reset_index().rename(columns={"OIL": "oil"}).sort_values("date")
    if not history_df.empty else pd.DataFrame(columns=["date", "oil"])
)

oil_change = water_change = gas_change = water_source_change = None
if not history_df.empty:
    dates = sorted(history_df["date"].unique())
    if len(dates) >= 2:
        prev_date, curr_date = dates[-2], dates[-1]
        prev_df = history_df[history_df["date"] == prev_date]
        curr_df = history_df[history_df["date"] == curr_date]
        oil_change          = int(curr_df["OIL"].sum())   - int(prev_df["OIL"].sum())
        gas_change          = int(curr_df["GAS"].sum())   - int(prev_df["GAS"].sum())
        water_change        = int(curr_df["WATER"].sum()) - int(prev_df["WATER"].sum())
        # water source needs HeaderID merge — use locations to filter
        ws_ids = locations_df.loc[locations_df["status"] == "Water Source", "UNIQUEID"].tolist()
        water_source_change = (
            int(curr_df.loc[curr_df["UNIQUEID"].isin(ws_ids), "WATER"].sum()) -
            int(prev_df.loc[prev_df["UNIQUEID"].isin(ws_ids), "WATER"].sum())
        )

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Oil Production",  f"{total_oil:,} BOPD",
          f"{oil_change:+,} BOPD vs yesterday" if oil_change is not None else None)
c2.metric("Total Gas Production",  f"{total_gas:,} MSCFD",
          f"{gas_change:+,} MSCFD vs yesterday" if gas_change is not None else None)
c3.metric("Total Water Production",f"{total_water:,} BWPD",
          f"{water_change:+,} BWPD vs yesterday" if water_change is not None else None)
c4.metric("Total Water Source",    f"{total_water_source:,} BWPD",
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

    field_totals = display_wells.groupby("field")["OIL"].sum().reset_index()
    field_order = ["North", "South", "East", "West"]
    field_totals["sort_key"] = field_totals["field"].apply(
        lambda f: next((i for i, k in enumerate(field_order) if k.lower() in f.lower()), len(field_order))
    )
    field_totals = field_totals.sort_values("sort_key").drop(columns="sort_key")
    fig_field = px.bar(field_totals, x="OIL", y="field", orientation="h",
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
        hover_name="ALIAS",
        hover_data={"field": True, "OIL": True, "water_cut_pct": True,
                    "latitude": False, "longitude": False},
        text="ALIAS", map_style="open-street-map",
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
    st.caption("No history yet — upload data to see the trend.")
else:
    trend_df = history_df.copy()
    trend_df["water_cut_pct"] = (
        trend_df["WATER"] / trend_df["bfpd"].replace(0, np.nan) * 100
    ).round(1).fillna(0)
    trend_agg = trend_df.groupby("date").agg(
        OIL=("OIL", "sum"), GAS=("GAS", "sum"),
        WATER=("WATER", "sum"), bfpd=("bfpd", "sum"),
        water_cut_pct=("water_cut_pct", "mean"),
    ).reset_index().sort_values("date")
    trend_agg["water_cut_pct"] = trend_agg["water_cut_pct"].round(1)

    t1, t2, t3, t4, t5 = st.tabs(["OIL", "GAS", "WATER", "BFPD", "Water Cut %"])

    def make_trend_fig(y_col, line_color, fill_color, y_title):
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=trend_agg["date"], y=trend_agg[y_col],
            mode="lines", fill="tozeroy",
            line=dict(color=line_color, width=2), fillcolor=fill_color,
        ))
        fig.update_layout(
            height=280, margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor="#0b1220", plot_bgcolor="#0b1220", font=dict(color="#94a3b8"),
            xaxis=dict(gridcolor="#263144"), yaxis=dict(gridcolor="#263144", title=y_title))
        return fig

    with t1:
        st.plotly_chart(make_trend_fig("OIL",   "#eab308", "rgba(234,179,8,0.2)",   "BOPD"),  use_container_width=True)
    with t2:
        st.plotly_chart(make_trend_fig("GAS",   "#f97316", "rgba(249,115,22,0.2)",  "MSCFD"), use_container_width=True)
    with t3:
        st.plotly_chart(make_trend_fig("WATER", "#38bdf8", "rgba(56,189,248,0.2)",  "BWPD"),  use_container_width=True)
    with t4:
        st.plotly_chart(make_trend_fig("bfpd",  "#22c55e", "rgba(34,197,94,0.2)",   "BFPD"),  use_container_width=True)
    with t5:
        fig_wc = go.Figure()
        fig_wc.add_trace(go.Scatter(
            x=trend_agg["date"], y=trend_agg["water_cut_pct"],
            mode="lines+markers", fill="tozeroy",
            line=dict(color="#ef4444", width=2), fillcolor="rgba(239,68,68,0.15)",
        ))
        fig_wc.update_layout(
            height=280, margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor="#0b1220", plot_bgcolor="#0b1220", font=dict(color="#94a3b8"),
            xaxis=dict(gridcolor="#263144"),
            yaxis=dict(gridcolor="#263144", title="Water Cut (%)", range=[0, 100]))
        st.plotly_chart(fig_wc, use_container_width=True)

# ----------------------------------------------------------------------------
# TOP PRODUCERS  +  WELL DECLINE TREND
# ----------------------------------------------------------------------------
top_col, detail_col = st.columns(2)

with top_col:
    st.subheader("Top Producing Wells")
    top_wells = filtered.sort_values("OIL", ascending=False).head(8)
    fig_top = px.bar(top_wells, x="ALIAS", y="OIL", color_discrete_sequence=["#eab308"])
    fig_top.update_layout(
        height=300, margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
        font=dict(color="#94a3b8"), xaxis_title=None, yaxis_title="OIL (BOPD)")
    st.plotly_chart(fig_top, use_container_width=True)

with detail_col:
    st.subheader("Well Decline Trend")
    top_well = filtered.sort_values("OIL", ascending=False).iloc[0]["ALIAS"] if not filtered.empty else filtered["ALIAS"].iloc[0]
    selected_alias = st.selectbox("Select a well", filtered["ALIAS"].tolist(),
                                  index=filtered["ALIAS"].tolist().index(top_well))
    sel_uniqueid = filtered.loc[filtered["ALIAS"] == selected_alias, "UNIQUEID"].iloc[0]
    well_history = (
        history_df[history_df["UNIQUEID"] == sel_uniqueid].sort_values("date").copy()
        if not history_df.empty else pd.DataFrame()
    )
    if well_history.empty:
        st.caption(f"No history yet for {selected_alias}.")
    else:
        well_history["water_cut_pct"] = (
            well_history["WATER"] / well_history["bfpd"].replace(0, np.nan) * 100
        ).round(1).fillna(0)

        w1, w2, w3, w4, w5 = st.tabs(["OIL", "GAS", "WATER", "BFPD", "Water Cut %"])

        def make_well_fig(y_col, line_color, fill_color, y_title):
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=well_history["date"], y=well_history[y_col],
                mode="lines+markers", fill="tozeroy",
                line=dict(color=line_color, width=2), fillcolor=fill_color,
            ))
            fig.update_layout(
                height=300, margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor="#0b1220", plot_bgcolor="#0b1220", font=dict(color="#94a3b8"),
                xaxis=dict(gridcolor="#263144"), yaxis=dict(gridcolor="#263144", title=y_title))
            return fig

        with w1:
            st.plotly_chart(make_well_fig("OIL",   "#eab308", "rgba(234,179,8,0.2)",  "BOPD"),  use_container_width=True)
        with w2:
            st.plotly_chart(make_well_fig("GAS",   "#f97316", "rgba(249,115,22,0.2)", "MSCFD"), use_container_width=True)
        with w3:
            st.plotly_chart(make_well_fig("WATER", "#38bdf8", "rgba(56,189,248,0.2)", "BWPD"),  use_container_width=True)
        with w4:
            st.plotly_chart(make_well_fig("bfpd",  "#22c55e", "rgba(34,197,94,0.2)",  "BFPD"),  use_container_width=True)
        with w5:
            fig_wc2 = go.Figure()
            fig_wc2.add_trace(go.Scatter(
                x=well_history["date"], y=well_history["water_cut_pct"],
                mode="lines+markers", fill="tozeroy",
                line=dict(color="#ef4444", width=2), fillcolor="rgba(239,68,68,0.15)",
            ))
            fig_wc2.update_layout(
                height=300, margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor="#0b1220", plot_bgcolor="#0b1220", font=dict(color="#94a3b8"),
                xaxis=dict(gridcolor="#263144"),
                yaxis=dict(gridcolor="#263144", title="Water Cut (%)", range=[0, 100]))
            st.plotly_chart(fig_wc2, use_container_width=True)

# ----------------------------------------------------------------------------
# WELL TABLE
# ----------------------------------------------------------------------------
st.subheader("Well List")
display_df = filtered[["ALIAS", "field", "status", "bfpd", "OIL", "GAS", "WATER",
                        "water_cut_pct", "last_test_date"]].rename(
    columns={"ALIAS": "Well", "field": "Field", "status": "Status",
             "bfpd": "BFPD", "OIL": "OIL (BOPD)", "GAS": "GAS (MSCFD)",
             "WATER": "WATER (BWPD)", "water_cut_pct": "Water Cut (%)",
             "last_test_date": "Last Test"}
)
st.dataframe(display_df, use_container_width=True, hide_index=True)

if using_sample:
    st.caption("⚠️ Showing sample data — connect to Supabase with real data to replace this.")
else:
    st.caption("✅ Showing live shared data from Supabase.")
