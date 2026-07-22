"""
Daily Production & Well Map Dashboard — Neon Postgres
------------------------------------------------------------------
Run locally:
    pip install streamlit pandas plotly numpy psycopg2-binary openpyxl

Neon tables needed:
    ProdWellBasiss : "Date" DATE, "UNIQUEID" TEXT, "OIL" NUMERIC, "GAS" NUMERIC, "WATER" NUMERIC
    HeaderID       : "UNIQUEID" TEXT, "ALIAS" TEXT, field TEXT, status TEXT,
                     latitude NUMERIC, longitude NUMERIC

Streamlit secrets (.streamlit/secrets.toml):
    [neon]
    url = "postgresql://neondb_owner:npg_vs0yrRMP6pte@ep-dawn-frost-aoz1ruri-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import numpy as np
import psycopg2

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
# DATABASE CONNECTION
# ----------------------------------------------------------------------------
def get_conn():
    """Fresh connection each call — Neon serverless handles pooling."""
    return psycopg2.connect(st.secrets["neon"]["url"])

def test_connection():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT 1 FROM "ProdWellBasiss" LIMIT 1')
        return True, "Connected"
    except Exception as e:
        return False, str(e)

# ----------------------------------------------------------------------------
# READ FUNCTIONS — plain SQL, no row limits
# ----------------------------------------------------------------------------
@st.cache_data(ttl=30, show_spinner=False)
def read_current():
    """Most recent row per well."""
    sql = """
        SELECT DISTINCT ON ("UNIQUEID")
            "Date"::text AS date,
            "UNIQUEID",
            "OIL"::float  AS "OIL",
            "GAS"::float  AS "GAS",
            "WATER"::float AS "WATER",
            "Date"::text  AS last_test_date
        FROM "ProdWellBasiss"
        ORDER BY "UNIQUEID", "Date" DESC
    """
    with get_conn() as conn:
        df = pd.read_sql(sql, conn)
    df["OIL"]   = pd.to_numeric(df["OIL"],   errors="coerce").fillna(0)
    df["GAS"]   = pd.to_numeric(df["GAS"],   errors="coerce").fillna(0)
    df["WATER"] = pd.to_numeric(df["WATER"], errors="coerce").fillna(0)
    df["bfpd"]          = df["OIL"] + df["WATER"]
    df["water_cut_pct"] = (df["WATER"] / df["bfpd"].replace(0, np.nan) * 100).round(1).fillna(0)
    return df

@st.cache_data(ttl=30, show_spinner=False)
def read_daily_totals():
    """Daily aggregated totals for trend charts."""
    sql = """
        SELECT
            "Date"::text         AS date,
            SUM("OIL")::float    AS "OIL",
            SUM("GAS")::float    AS "GAS",
            SUM("WATER")::float  AS "WATER"
        FROM "ProdWellBasiss"
        GROUP BY "Date"
        ORDER BY "Date"
    """
    with get_conn() as conn:
        df = pd.read_sql(sql, conn)
    for col in ["OIL", "GAS", "WATER"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["bfpd"]          = df["OIL"] + df["WATER"]
    df["water_cut_pct"] = (df["WATER"] / df["bfpd"].replace(0, np.nan) * 100).round(1).fillna(0)
    return df

@st.cache_data(ttl=30, show_spinner=False)
def read_locations():
    sql = 'SELECT "UNIQUEID", "ALIAS", field, status, latitude::float, longitude::float FROM "HeaderID"'
    with get_conn() as conn:
        df = pd.read_sql(sql, conn)
    return df

@st.cache_data(ttl=30, show_spinner=False)
def read_snapshot(date_str: str):
    """All wells for a specific date."""
    sql = """
        SELECT
            "UNIQUEID",
            "OIL"::float   AS "OIL",
            "GAS"::float   AS "GAS",
            "WATER"::float AS "WATER"
        FROM "ProdWellBasiss"
        WHERE "Date"::text = %(d)s
    """
    with get_conn() as conn:
        df = pd.read_sql(sql, conn, params={"d": date_str})
    for col in ["OIL", "GAS", "WATER"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["bfpd"]          = df["OIL"] + df["WATER"]
    df["water_cut_pct"] = (df["WATER"] / df["bfpd"].replace(0, np.nan) * 100).round(1).fillna(0)
    df["last_test_date"] = date_str
    return df

@st.cache_data(ttl=30, show_spinner=False)
def read_well_history(uid: str):
    """Full history for one well — for decline trend chart."""
    sql = """
        SELECT
            "Date"::text   AS date,
            "OIL"::float   AS "OIL",
            "GAS"::float   AS "GAS",
            "WATER"::float AS "WATER"
        FROM "ProdWellBasiss"
        WHERE "UNIQUEID" = %(uid)s
        ORDER BY "Date"
    """
    with get_conn() as conn:
        df = pd.read_sql(sql, conn, params={"uid": uid})
    for col in ["OIL", "GAS", "WATER"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["bfpd"]          = df["OIL"] + df["WATER"]
    df["water_cut_pct"] = (df["WATER"] / df["bfpd"].replace(0, np.nan) * 100).round(1).fillna(0)
    return df

# ----------------------------------------------------------------------------
# SAMPLE DATA (fallback when DB is empty)
# ----------------------------------------------------------------------------
@st.cache_data
def generate_sample_data():
    rng = np.random.default_rng(42)
    names = ["M-01","M-02","M-03","M-04","M-05","M-06","M-07","M-08","M-09","M-10"]
    base = []
    for name in names:
        r = rng.integers(80, 500)
        oil, gas, water = int(r), int(r * 0.1), int(r * 0.3)
        base.append({"UNIQUEID": name, "OIL": oil, "GAS": gas, "WATER": water,
                     "last_test_date": "2026-06-14"})
    cur = pd.DataFrame(base)
    hist_rows = []
    for d in range(30):
        ds = (datetime(2026, 6, 14) - pd.Timedelta(days=29 - d)).strftime("%Y-%m-%d")
        for row in base:
            hist_rows.append({**row, "date": ds})
    hist = pd.DataFrame(hist_rows).drop(columns=["last_test_date"])
    for df in [cur, hist]:
        df["bfpd"]          = df["OIL"] + df["WATER"]
        df["water_cut_pct"] = (df["WATER"] / df["bfpd"].replace(0, np.nan) * 100).round(1).fillna(0)
    return cur, hist

@st.cache_data
def generate_sample_locations():
    rng   = np.random.default_rng(42)
    names = ["M-01","M-02","M-03","M-04","M-05","M-06","M-07","M-08","M-09","M-10"]
    stats = ["Oil","Oil","Shut-in","Oil","Oil","Down","Injector","Oil","Water Source","Oil"]
    fields = ["North Block","South Block","East Flank"]
    return pd.DataFrame([{
        "UNIQUEID": n, "ALIAS": n, "field": fields[i % 3], "status": stats[i],
        "latitude":  -2.5 + (i % 4) * 0.04 + rng.random() * 0.01,
        "longitude": 110.5 + (i // 4) * 0.05 + rng.random() * 0.01,
    } for i, n in enumerate(names)])

# ----------------------------------------------------------------------------
# SIDEBAR — CONNECTION STATUS
# ----------------------------------------------------------------------------
with st.sidebar:
    ok, msg = test_connection()
    if ok:
        st.success("✅ Neon connected")
    else:
        st.error(f"❌ {msg}")

# ----------------------------------------------------------------------------
# LOAD DATA
# ----------------------------------------------------------------------------
try:
    wells_df     = read_current()
    history_df   = read_daily_totals()
    locations_df = read_locations()
    db_connected = True
except Exception as e:
    st.error(f"Couldn't connect to Neon — check your secrets. Details: {e}")
    wells_df     = None
    history_df   = pd.DataFrame()
    locations_df = pd.DataFrame()
    db_connected = False

using_sample = wells_df is None or wells_df.empty
if using_sample:
    wells_df, history_df = generate_sample_data()
    locations_df = generate_sample_locations()
    if db_connected:
        st.info("No data yet — import rows into ProdWellBasiss and HeaderID in Neon.")

wells_df = wells_df.merge(locations_df, on="UNIQUEID", how="left")

missing_coords = wells_df["latitude"].isna() | wells_df["longitude"].isna()
if missing_coords.any() and not using_sample:
    st.warning("Wells with no coordinates: "
               + ", ".join(wells_df.loc[missing_coords, "ALIAS"].fillna("?").tolist())
               + ". Add them to HeaderID.")

# ----------------------------------------------------------------------------
# HEADER
# ----------------------------------------------------------------------------
col_title, col_date, col_filter = st.columns([3, 1, 1])
with col_title:
    st.title("Daily Production Dashboard")
    st.caption("· Shared live dashboard · " + datetime.now().strftime("%A, %B %d, %Y"))
with col_date:
    available = sorted(history_df["date"].unique(), reverse=True) if not history_df.empty else []
    if available:
        avail_dt = [datetime.strptime(d, "%Y-%m-%d").date() for d in available]
        sel_date = st.date_input("Snapshot date",
                                 value=avail_dt[0], min_value=avail_dt[-1], max_value=avail_dt[0])
        sel_date_str = sel_date.strftime("%Y-%m-%d")
    else:
        sel_date_str = None
with col_filter:
    field_opts = ["All"] + sorted(wells_df["field"].dropna().unique().tolist())
    field_filter = st.selectbox("Field", field_opts)

# Snapshot filter
if sel_date_str and not using_sample:
    try:
        snap = read_snapshot(sel_date_str)
        snap = snap.merge(locations_df, on="UNIQUEID", how="left")
        display_wells = snap
    except Exception:
        display_wells = wells_df
else:
    display_wells = wells_df

filtered = display_wells if field_filter == "All" else display_wells[display_wells["field"] == field_filter]

# ----------------------------------------------------------------------------
# SUMMARY METRICS
# ----------------------------------------------------------------------------
total_oil   = int(filtered["OIL"].sum())
total_gas   = int(filtered["GAS"].sum())
total_water = int(filtered["WATER"].sum())
total_water_source = int(filtered.loc[filtered["status"] == "Water Source", "WATER"].sum())

oil_change = gas_change = water_change = water_source_change = None
if not history_df.empty and len(history_df) >= 2:
    prev, curr = history_df.iloc[-2], history_df.iloc[-1]
    oil_change          = int(curr["OIL"])   - int(prev["OIL"])
    gas_change          = int(curr["GAS"])   - int(prev["GAS"])
    water_change        = int(curr["WATER"]) - int(prev["WATER"])

r1c1, r1c2, r1c3, r1c4 = st.columns(4)
r1c1.metric("Total Oil Production",   f"{total_oil:,} BOPD",
            f"{oil_change:+,} BOPD vs yesterday"   if oil_change   is not None else None)
r1c2.metric("Total Gas Production",   f"{total_gas:,} Mscfd",
            f"{gas_change:+,} Mscfd vs yesterday"  if gas_change   is not None else None)
r1c3.metric("Total Water Production", f"{total_water:,} BWPD",
            f"{water_change:+,} BWPD vs yesterday" if water_change is not None else None)
r1c4.metric("Total Water Source",     f"{total_water_source:,} BWPD")

st.markdown("")

# ----------------------------------------------------------------------------
# STATUS & FIELD TOTALS  +  WELL MAP
# ----------------------------------------------------------------------------
pie_col, map_col = st.columns([1, 1.3])

with pie_col:
    st.subheader("Status & Field Totals")
    sc = filtered["status"].value_counts().reset_index()
    sc.columns = ["status", "count"]
    fig_pie = px.pie(sc, names="status", values="count",
                     color="status", color_discrete_map=STATUS_COLORS, hole=0.55)
    fig_pie.update_traces(texttemplate="%{label}: %{value}", textposition="outside",
                          hovertemplate="%{label}: %{value} wells<extra></extra>")
    fig_pie.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=0),
                          paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
                          legend=dict(font=dict(color="#e2e8f0"), orientation="h"),
                          font=dict(color="#e2e8f0"))
    st.plotly_chart(fig_pie, use_container_width=True)

    ft = display_wells.groupby("field")["OIL"].sum().reset_index()
    fo = ["North", "South", "East", "West"]
    ft["sk"] = ft["field"].apply(
        lambda f: next((i for i, k in enumerate(fo) if k.lower() in f.lower()), len(fo)))
    ft = ft.sort_values("sk").drop(columns="sk")
    fig_field = px.bar(ft, x="OIL", y="field", orientation="h",
                       color_discrete_sequence=["#38bdf8"])
    fig_field.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=0),
                             paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
                             font=dict(color="#94a3b8"), xaxis_title=None, yaxis_title=None,
                             yaxis=dict(categoryorder="array",
                                        categoryarray=ft["field"].tolist()[::-1]))
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
        map=dict(style="white-bg", layers=[{
            "below": "traces", "sourcetype": "raster",
            "sourceattribution": "Esri, Maxar, Earthstar Geographics",
            "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
        }]),
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
if history_df.empty:
    st.caption("No history yet.")
else:
    t1, t2, t3, t4, t5 = st.tabs(["OIL", "GAS", "WATER", "BFPD", "Water Cut %"])

    def make_trend_fig(y_col, lc, fc, yt):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=history_df["date"], y=history_df[y_col],
                                  mode="lines", fill="tozeroy",
                                  line=dict(color=lc, width=2), fillcolor=fc))
        fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0),
                           paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
                           font=dict(color="#94a3b8"),
                           xaxis=dict(gridcolor="#263144"),
                           yaxis=dict(gridcolor="#263144", title=yt))
        return fig

    with t1: st.plotly_chart(make_trend_fig("OIL",   "#eab308","rgba(234,179,8,0.2)",  "OIL (BOPD)"),  use_container_width=True)
    with t2: st.plotly_chart(make_trend_fig("GAS",   "#f97316","rgba(249,115,22,0.2)", "GAS (Mscfd)"), use_container_width=True)
    with t3: st.plotly_chart(make_trend_fig("WATER", "#38bdf8","rgba(56,189,248,0.2)", "WATER (BWPD)"),use_container_width=True)
    with t4: st.plotly_chart(make_trend_fig("bfpd",  "#22c55e","rgba(34,197,94,0.2)",  "BFPD"),        use_container_width=True)
    with t5:
        fig_wc = go.Figure()
        fig_wc.add_trace(go.Scatter(x=history_df["date"], y=history_df["water_cut_pct"],
                                     mode="lines+markers", fill="tozeroy",
                                     line=dict(color="#ef4444", width=2),
                                     fillcolor="rgba(239,68,68,0.15)"))
        fig_wc.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0),
                              paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
                              font=dict(color="#94a3b8"), xaxis=dict(gridcolor="#263144"),
                              yaxis=dict(gridcolor="#263144", title="Water Cut (%)", range=[0,100]))
        st.plotly_chart(fig_wc, use_container_width=True)

# ----------------------------------------------------------------------------
# TOP PRODUCERS  +  WELL DECLINE TREND
# ----------------------------------------------------------------------------
top_col, detail_col = st.columns(2)

with top_col:
    st.subheader("Top Producing Wells")
    tw = filtered.sort_values("OIL", ascending=False).head(8)
    fig_top = px.bar(tw, x="ALIAS", y="OIL", color_discrete_sequence=["#eab308"])
    fig_top.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0),
                           paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
                           font=dict(color="#94a3b8"), xaxis_title=None, yaxis_title="OIL (BOPD)")
    st.plotly_chart(fig_top, use_container_width=True)

with detail_col:
    st.subheader("Well Decline Trend")
    alias_list = filtered["ALIAS"].dropna().tolist()
    top_alias  = filtered.sort_values("OIL", ascending=False).iloc[0]["ALIAS"] \
                 if not filtered.empty else alias_list[0]
    sel_alias  = st.selectbox("Select a well", alias_list,
                               index=alias_list.index(top_alias) if top_alias in alias_list else 0)

    uid_match = filtered.loc[filtered["ALIAS"] == sel_alias, "UNIQUEID"]
    if not uid_match.empty and not using_sample:
        wh = read_well_history(uid_match.iloc[0])
    else:
        wh = pd.DataFrame()

    if wh.empty:
        st.caption(f"No history for {sel_alias}.")
    else:
        w1, w2, w3, w4, w5 = st.tabs(["OIL", "GAS", "WATER", "BFPD", "Water Cut %"])

        def make_well_fig(y_col, lc, fc, yt):
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=wh["date"], y=wh[y_col],
                                      mode="lines+markers", fill="tozeroy",
                                      line=dict(color=lc, width=2), fillcolor=fc))
            fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0),
                               paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
                               font=dict(color="#94a3b8"),
                               xaxis=dict(gridcolor="#263144"),
                               yaxis=dict(gridcolor="#263144", title=yt))
            return fig

        with w1: st.plotly_chart(make_well_fig("OIL",   "#eab308","rgba(234,179,8,0.2)",  "OIL (BOPD)"),  use_container_width=True)
        with w2: st.plotly_chart(make_well_fig("GAS",   "#f97316","rgba(249,115,22,0.2)", "GAS (Mscfd)"), use_container_width=True)
        with w3: st.plotly_chart(make_well_fig("WATER", "#38bdf8","rgba(56,189,248,0.2)", "WATER (BWPD)"),use_container_width=True)
        with w4: st.plotly_chart(make_well_fig("bfpd",  "#22c55e","rgba(34,197,94,0.2)",  "BFPD"),        use_container_width=True)
        with w5:
            fig_wc2 = go.Figure()
            fig_wc2.add_trace(go.Scatter(x=wh["date"], y=wh["water_cut_pct"],
                                          mode="lines+markers", fill="tozeroy",
                                          line=dict(color="#ef4444", width=2),
                                          fillcolor="rgba(239,68,68,0.15)"))
            fig_wc2.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0),
                                   paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
                                   font=dict(color="#94a3b8"), xaxis=dict(gridcolor="#263144"),
                                   yaxis=dict(gridcolor="#263144", title="Water Cut (%)", range=[0,100]))
            st.plotly_chart(fig_wc2, use_container_width=True)

# ----------------------------------------------------------------------------
# WELL TABLE
# ----------------------------------------------------------------------------
st.subheader("Well List")
disp = filtered[["ALIAS","field","status","bfpd","OIL","GAS","WATER",
                  "water_cut_pct","last_test_date"]].rename(columns={
    "ALIAS":"Well","field":"Field","status":"Status",
    "bfpd":"BFPD","OIL":"OIL (BOPD)","GAS":"GAS (Mscfd)","WATER":"WATER (BWPD)",
    "water_cut_pct":"Water Cut (%)","last_test_date":"Last Test"
})
st.dataframe(disp, use_container_width=True, hide_index=True)

if using_sample:
    st.caption("⚠️ Showing sample data — connect Neon and import your data.")
else:
    st.caption("✅ Showing live data from Neon Postgres.")
