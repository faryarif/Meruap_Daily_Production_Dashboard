"""
Daily Production & Well Map Dashboard — Shared via Supabase
------------------------------------------------------------------
Run locally:
    pip install streamlit pandas plotly numpy supabase openpyxl

Supabase tables needed:
    - ProdWellBasiss : id, date, ALIAS, OIL, WATER, injection_rate  (bfpd = OIL + WATER)
    - HeaderID      : ALIAS, field, status, latitude, longitude

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

DATA_PROD_COLS     = ["date", "ALIAS", "OIL", "WATER", "injection_rate"]
LOCATION_HEAD_COLS = ["ALIAS", "field", "status", "latitude", "longitude"]

if "selected_well" not in st.session_state:
    st.session_state.selected_well = None

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

# FIX 1: use correct table name in test_connection
def test_connection():
    try:
        get_supabase().table("ProdWellBasiss").select("ALIAS").limit(1).execute()
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
        "date, ALIAS, OIL, WATER, injection_rate"
    ).order("date").execute()
    if not resp.data:
        return None, pd.DataFrame(columns=DATA_PROD_COLS)
    df = pd.DataFrame(resp.data)
    for col in ["OIL", "WATER", "injection_rate"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    latest_date = df["date"].max()
    current_df = df[df["date"] == latest_date].drop(columns=["date"]).reset_index(drop=True)
    return current_df, df

@st.cache_data(ttl=30, show_spinner=False)
def read_locations():
    client = get_supabase()
    resp = client.table("HeaderID").select(
        "ALIAS, field, status, latitude, longitude"
    ).execute()
    if not resp.data:
        return pd.DataFrame(columns=LOCATION_HEAD_COLS)
    df = pd.DataFrame(resp.data)
    for col in ["latitude", "longitude"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

# ----------------------------------------------------------------------------
# FIX 2: sample data generators (previously missing, caused NameError)
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
        water_val = int(bopd_val * 0.3) if status == "Oil" else 0
        base_rows.append({
            "ALIAS": name,
            "OIL": bopd_val, "WATER": water_val,
            "injection_rate": int(base_rate * 0.8) if status in ("Injector", "Water Source") else 0,
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
    rows = []
    for i, name in enumerate(names):
        rng.integers(80, 500)  # discarded — keeps draw sequence aligned with generate_sample_data
        roll = rng.random()
        status = "Down" if roll > 0.85 else "Shut-in" if roll > 0.75 else "Oil"
        rows.append({
            "ALIAS": name, "field": fields[i % 3], "status": status,
            "latitude": -2.5 + (i % 4) * 0.04 + rng.random() * 0.01,
            "longitude": 110.5 + (i // 4) * 0.05 + rng.random() * 0.01,
        })
    return pd.DataFrame(rows)

# ----------------------------------------------------------------------------
# FIX 3: call test_connection in sidebar so it's actually used
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
    history_df = pd.DataFrame(columns=DATA_PROD_COLS)
    locations_df = pd.DataFrame(columns=LOCATION_HEAD_COLS)
    db_connected = False

using_sample = wells_df is None or wells_df.empty
if using_sample:
    wells_df, history_df = generate_sample_data()
    locations_df = generate_sample_locations()
    if db_connected:
        st.info("No data yet — showing sample data. Upload a file in the sidebar.")

if "injection_rate" not in wells_df.columns:
    wells_df["injection_rate"] = 0

if not history_df.empty:
    history_df = history_df.merge(locations_df[["ALIAS", "status"]], on="ALIAS", how="left")
    history_df["status"] = history_df["status"].fillna("Unknown")
    history_df["bfpd"] = history_df["OIL"] + history_df["WATER"]

wells_df["bfpd"] = wells_df["OIL"] + wells_df["WATER"]
wells_df = wells_df.merge(locations_df, on="ALIAS", how="left")
wells_df["water_cut_pct"] = (
    wells_df["WATER"] / wells_df["bfpd"].replace(0, np.nan) * 100
).round(1).fillna(0)

missing_coords = wells_df["latitude"].isna() | wells_df["longitude"].isna()
if missing_coords.any() and not using_sample:
    st.warning(
        "These wells have no saved coordinates: "
        + ", ".join(wells_df.loc[missing_coords, "ALIAS"].tolist())
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
    snap_df = history_df[history_df["date"] == selected_date_str].drop(columns=["date", "status"]).reset_index(drop=True)
    if "injection_rate" not in snap_df.columns:
        snap_df["injection_rate"] = 0
    snap_df = snap_df.merge(locations_df, on="ALIAS", how="left")
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
total_bopd         = int(filtered["OIL"].sum())
active_count       = int((filtered["status"] == "Oil").sum())
shutin_count       = int((filtered["status"] == "Shut-in").sum())
down_count         = int((filtered["status"] == "Down").sum())
injector_count     = int((filtered["status"] == "Injector").sum())
water_source_count = int((filtered["status"] == "Water Source").sum())
total_injection    = int(filtered.loc[filtered["status"] == "Injector", "injection_rate"].sum())
total_water_source = int(filtered.loc[filtered["status"] == "Water Source", "WATER"].sum())
total_water_production = int(filtered["WATER"].sum())

agg_history = (
    history_df.groupby("date")["OIL"].sum().reset_index().sort_values("date")
    if not history_df.empty else pd.DataFrame(columns=["date", "OIL"])
)

bopd_change = injection_change = water_prod_change = water_source_change = None
if not history_df.empty:
    dates = sorted(history_df["date"].unique())
    if len(dates) >= 2:
        prev_date, curr_date = dates[-2], dates[-1]
        prev_df = history_df[history_df["date"] == prev_date].copy()
        curr_df = history_df[history_df["date"] == curr_date].copy()
        bopd_change         = int(curr_df["OIL"].sum()) - int(prev_df["OIL"].sum())
        injection_change    = int(curr_df.loc[curr_df["status"] == "Injector", "injection_rate"].sum()) - \
                              int(prev_df.loc[prev_df["status"] == "Injector", "injection_rate"].sum())
        water_prod_change   = int(curr_df["WATER"].sum()) - int(prev_df["WATER"].sum())
        water_source_change = int(curr_df.loc[curr_df["status"] == "Water Source", "WATER"].sum()) - \
                              int(prev_df.loc[prev_df["status"] == "Water Source", "WATER"].sum())

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
    marker_sizes = [22 if a == st.session_state.selected_well else 13 for a in mappable["ALIAS"]]
    fig_map = px.scatter_map(
        mappable, lat="latitude", lon="longitude", color="status",
        color_discrete_map=STATUS_COLORS, size=marker_sizes, size_max=18,
        hover_name="ALIAS",
        hover_data={"field": True, "OIL": True, "water_cut_pct": True,
                    "latitude": False, "longitude": False},
        text="ALIAS", map_style="open-street-map",
        custom_data=["ALIAS"],
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
    map_event = st.plotly_chart(
        fig_map, use_container_width=True,
        on_select="rerun", selection_mode="points", key="well_map_chart",
    )
    clicked_points = (map_event or {}).get("selection", {}).get("points", []) if map_event else []
    if clicked_points:
        clicked_alias = clicked_points[0].get("customdata", [None])[0]
        if clicked_alias and clicked_alias != st.session_state.selected_well:
            st.session_state.selected_well = clicked_alias
            st.rerun()

    if st.session_state.selected_well and st.session_state.selected_well in filtered["ALIAS"].values:
        sel = filtered[filtered["ALIAS"] == st.session_state.selected_well].iloc[0]
        status_color = STATUS_COLORS.get(sel["status"], "#94a3b8")
        st.markdown(
            f"""<div style="margin-top:10px;padding:10px;background:#141d2e;
            border:1px solid #263144;border-radius:8px;font-size:13px;">
            <strong>{sel['ALIAS']}</strong> · {sel['field']} ·
            <span style="color:{status_color};font-weight:600;">{sel['status']}</span> ·
            {int(sel['OIL']):,} BOPD · Water cut {sel['water_cut_pct']}%
            </div>""",
            unsafe_allow_html=True,
        )
    else:
        st.caption("Click any well marker on the map to see its details and decline trend below.")

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
        bfpd=("bfpd", "sum"), OIL=("OIL", "sum"),
        WATER=("WATER", "sum"), water_cut_pct=("water_cut_pct", "mean"),
    ).reset_index().sort_values("date")
    trend_agg["water_cut_pct"] = trend_agg["water_cut_pct"].round(1)

    trend_tab1, trend_tab2, trend_tab3, trend_tab4 = st.tabs(["BOPD", "BFPD", "BWPD", "Water Cut %"])

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

    with trend_tab1:
        st.plotly_chart(make_trend_fig("OIL", "#eab308", "rgba(234,179,8,0.2)",  "BOPD"), use_container_width=True)
    with trend_tab2:
        st.plotly_chart(make_trend_fig("bfpd", "#22c55e", "rgba(34,197,94,0.2)",  "BFPD"), use_container_width=True)
    with trend_tab3:
        st.plotly_chart(make_trend_fig("WATER", "#38bdf8", "rgba(56,189,248,0.2)", "BWPD"), use_container_width=True)
    with trend_tab4:
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
# INJECTION RATE TREND
# ----------------------------------------------------------------------------
st.subheader("Injection Rate Trend")
if history_df.empty:
    st.caption("No history yet — upload data to see the trend.")
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
            paper_bgcolor="#0b1220", plot_bgcolor="#0b1220", font=dict(color="#94a3b8"),
            xaxis=dict(gridcolor="#263144"), yaxis=dict(gridcolor="#263144", title="Injection Rate"),
            legend=dict(font=dict(color="#e2e8f0"), orientation="h"))
        st.plotly_chart(fig_inj, use_container_width=True)

# ----------------------------------------------------------------------------
# TOP PRODUCERS  +  WELL DECLINE TREND
# ----------------------------------------------------------------------------
top_col, detail_col = st.columns(2)

with top_col:
    st.subheader("Top Producing Wells")
    top_wells = filtered.sort_values("OIL", ascending=False).head(8)
    fig_top = px.bar(top_wells, x="ALIAS", y="OIL", color_discrete_sequence=["#38bdf8"])
    fig_top.update_layout(
        height=300, margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
        font=dict(color="#94a3b8"), xaxis_title=None, yaxis_title="BOPD")
    st.plotly_chart(fig_top, use_container_width=True)

with detail_col:
    st.subheader("Well Decline Trend")
    well_options = filtered["ALIAS"].tolist()
    if not well_options:
        st.caption("No wells to display for this filter.")
        selected_well = None
    else:
        top_well = filtered.sort_values("OIL", ascending=False).iloc[0]["ALIAS"]
        default_well = st.session_state.selected_well if st.session_state.selected_well in well_options else top_well
        selected_well = st.selectbox("Select a well", well_options,
                                     index=well_options.index(default_well),
                                     key="well_selectbox")
        st.session_state.selected_well = selected_well
    well_history = (
        history_df[history_df["ALIAS"] == selected_well].sort_values("date").copy()
        if selected_well and not history_df.empty else pd.DataFrame()
    )
    if well_history.empty:
        if selected_well:
            st.caption(f"No history yet for {selected_well}.")
    else:
        well_history["water_cut_pct"] = (
            well_history["WATER"] / well_history["bfpd"].replace(0, np.nan) * 100
        ).round(1).fillna(0)

        w_tab1, w_tab2, w_tab3, w_tab4 = st.tabs(["BOPD", "BFPD", "BWPD", "Water Cut %"])

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

        with w_tab1:
            st.plotly_chart(make_well_fig("OIL", "#eab308", "rgba(234,179,8,0.2)",  "BOPD"), use_container_width=True)
        with w_tab2:
            st.plotly_chart(make_well_fig("bfpd", "#22c55e", "rgba(34,197,94,0.2)",  "BFPD"), use_container_width=True)
        with w_tab3:
            st.plotly_chart(make_well_fig("WATER", "#38bdf8", "rgba(56,189,248,0.2)", "BWPD"), use_container_width=True)
        with w_tab4:
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
display_df = filtered[["ALIAS", "field", "status", "bfpd", "OIL", "WATER",
                        "water_cut_pct", "injection_rate"]].rename(
    columns={"ALIAS": "Well", "field": "Field", "status": "Status",
             "bfpd": "BFPD", "OIL": "BOPD", "WATER": "BWPD",
             "water_cut_pct": "Water Cut (%)", "injection_rate": "Injection Rate"}
)
st.dataframe(display_df, use_container_width=True, hide_index=True)

if using_sample:
    st.caption("⚠️ Showing sample data — upload a file in the ETL page to load real data.")
else:
    st.caption("✅ Showing live shared data from Supabase.")
