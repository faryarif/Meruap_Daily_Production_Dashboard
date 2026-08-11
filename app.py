"""Daily Production & Well Map Dashboard."""
from datetime import datetime
import pandas as pd
import streamlit as st
from charts import make_field_totals_bar, make_injection_trend_fig, make_status_pie, make_top_wells_bar, make_trend_fig, make_water_cut_trend_fig, make_well_history_fig
from constants import APP_TITLE, DATA_PROD_COLS, LOCATION_HEAD_COLS, PAGE_ICON
from database import read_daily_trend, read_snapshot, read_locations, read_well_history
from helpers import filter_by_field, field_options, missing_coordinate_aliases
from maps import make_well_map
from metrics import calculate_daily_changes, calculate_kpis
from styles import inject_styles

st.set_page_config(page_title=APP_TITLE, page_icon=PAGE_ICON, layout="wide", initial_sidebar_state="collapsed")
inject_styles(st)

try:
    locations_df = read_locations()
    trend_df = read_daily_trend()
    dates = sorted(trend_df["date"].dropna().unique(), reverse=True) if not trend_df.empty else []
    wells_df = read_snapshot(dates[0]) if dates else pd.DataFrame(columns=DATA_PROD_COLS)
except Exception as exc:
    st.error(f"Couldn't load dashboard data. Check your Supabase connection/query configuration. Details: {exc}")
    wells_df = pd.DataFrame(columns=DATA_PROD_COLS)
    trend_df = pd.DataFrame()
    locations_df = pd.DataFrame(columns=LOCATION_HEAD_COLS)

if wells_df.empty:
    st.warning("No production snapshot is available in Supabase.")
    st.stop()

col_title, col_date, col_filter = st.columns([3, 1, 1])
with col_title:
    st.title("Daily Production Dashboard")
    st.caption("· Shared live dashboard · " + datetime.now().strftime("%A, %B %d, %Y"))
with col_date:
    date_values = [datetime.strptime(d, "%Y-%m-%d").date() for d in dates]
    selected_date = st.date_input("Snapshot date", value=date_values[0], min_value=date_values[-1], max_value=date_values[0])
    selected_date_str = selected_date.strftime("%Y-%m-%d")
with col_filter:
    field_filter = st.selectbox("Field", field_options(wells_df))

display_wells = wells_df if selected_date_str == dates[0] else read_snapshot(selected_date_str)
filtered = filter_by_field(display_wells, field_filter)
kpis = calculate_kpis(filtered)
changes = calculate_daily_changes(trend_df)
missing_aliases = missing_coordinate_aliases(display_wells)
if missing_aliases:
    st.warning("These wells have no saved coordinates: " + ", ".join(missing_aliases) + ". Add them to the 'HeaderID' table in Supabase.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Production", f"{kpis['total_bopd']:,} BOPD", f"{changes['bopd_change']:+,} BOPD vs yesterday" if changes["bopd_change"] is not None else None)
c2.metric("Total Injection", f"{kpis['total_injection']:,} Barrels", f"{changes['injection_change']:+,} Barrels vs yesterday" if changes["injection_change"] is not None else None)
c3.metric("Total Water Production", f"{kpis['total_water_production']:,} BWPD", f"{changes['water_prod_change']:+,} BWPD vs yesterday" if changes["water_prod_change"] is not None else None)
c4.metric("Total Water Source", f"{kpis['total_water_source']:,} BWPD", f"{changes['water_source_change']:+,} BWPD vs yesterday" if changes["water_source_change"] is not None else None)

pie_col, map_col = st.columns([1, 1.3])
with pie_col:
    st.subheader("Status & Field Totals")
    st.plotly_chart(make_status_pie(filtered), use_container_width=True)
    st.plotly_chart(make_field_totals_bar(display_wells), use_container_width=True)
with map_col:
    st.subheader("Well Map")
    st.plotly_chart(make_well_map(filtered), use_container_width=True)

st.subheader("Total Production Trend")
if trend_df.empty:
    st.caption("No history yet - upload data to see the trend.")
else:
    trend_agg = trend_df.copy()
    trend_agg["OIL"] = pd.to_numeric(trend_agg["OIL"], errors="coerce").fillna(0.0)
    trend_agg["WATER"] = pd.to_numeric(trend_agg["WATER"], errors="coerce").fillna(0.0)
    trend_agg["bfpd"] = trend_agg["OIL"] + trend_agg["WATER"]
    # Avoid pandas nullable NAType here: replace zero denominators with NaN.
    bfpd = trend_agg["bfpd"]
    trend_agg["water_cut_pct"] = (trend_agg["WATER"] / bfpd.where(bfpd.ne(0), float("nan")) * 100.0).round(1).fillna(0.0)
    t1, t2, t3, t4 = st.tabs(["BOPD", "BFPD", "BWPD", "Water Cut %"])
    with t1: st.plotly_chart(make_trend_fig(trend_agg, "OIL", "#22c55e", "rgba(34,197,94,0.2)", "BOPD"), use_container_width=True)
    with t2: st.plotly_chart(make_trend_fig(trend_agg, "bfpd", "#eab308", "rgba(234,179,8,0.2)", "BFPD"), use_container_width=True)
    with t3: st.plotly_chart(make_trend_fig(trend_agg, "WATER", "#38bdf8", "rgba(56,189,248,0.2)", "BWPD"), use_container_width=True)
    with t4: st.plotly_chart(make_water_cut_trend_fig(trend_agg), use_container_width=True)

st.subheader("Injection Rate Trend")
if not trend_df.empty:
    inj_by_date = pd.concat([
        trend_df[["date", "injection_rate"]].assign(status="Injector"),
        trend_df[["date", "water_source_rate"]].assign(status="Water Source").rename(columns={"water_source_rate": "injection_rate"})
    ], ignore_index=True)
    inj_by_date = inj_by_date[inj_by_date["injection_rate"] > 0]
    if inj_by_date.empty: st.caption("No Injector or Water Source wells found in data yet.")
    else: st.plotly_chart(make_injection_trend_fig(inj_by_date), use_container_width=True)
else:
    st.caption("No history yet - upload data to see the trend.")

top_col, detail_col = st.columns(2)
with top_col:
    st.subheader("Top Producing Wells")
    st.plotly_chart(make_top_wells_bar(filtered), use_container_width=True)
with detail_col:
    st.subheader("Well Decline Trend")
    options = filtered["ALIAS"].tolist()
    selected_well = None
    if options:
        top_well = filtered.sort_values("OIL", ascending=False).iloc[0]["ALIAS"]
        selected_well = st.selectbox("Select a well", options, index=options.index(top_well))
    else:
        st.caption("No wells to display for this filter.")
    well_history = read_well_history(selected_well) if selected_well else pd.DataFrame()
    if well_history.empty and selected_well:
        st.caption(f"No history yet for {selected_well}.")
    elif not well_history.empty:
        well_history = well_history.sort_values("date")
        w1, w2, w3, w4 = st.tabs(["BOPD", "BFPD", "BWPD", "Water Cut %"])
        with w1: st.plotly_chart(make_well_history_fig(well_history, "OIL", "#22c55e", "rgba(34,197,94,0.2)", "BOPD"), use_container_width=True)
        with w2: st.plotly_chart(make_well_history_fig(well_history, "bfpd", "#eabf00", "rgba(234,179,8,0.2)", "BFPD"), use_container_width=True)
        with w3: st.plotly_chart(make_well_history_fig(well_history, "WATER", "#38bdf8", "rgba(56,189,248,0.2)", "BWPD"), use_container_width=True)
        with w4: st.plotly_chart(make_well_history_fig(well_history, "water_cut_pct", "#ef4444", "rgba(239,68,68,0.15)", "Water Cut (%)"), use_container_width=True)

st.subheader("Well Data")
table_cols = ["ALIAS", "field", "status", "OIL", "WATER", "bfpd", "water_cut_pct", "injection_rate", "latitude", "longitude"]
visible_cols = [c for c in table_cols if c in filtered.columns]
st.dataframe(filtered[visible_cols].sort_values("OIL", ascending=False), use_container_width=True, hide_index=True)
