"""Daily Production & Well Map Dashboard."""
from datetime import datetime
import pandas as pd
import streamlit as st
from charts import make_field_totals_bar, make_injection_trend_fig, make_status_pie, make_top_wells_bar, make_trend_fig, make_water_cut_trend_fig, make_well_history_fig
from constants import APP_TITLE, DATA_PROD_COLS, LOCATION_HEAD_COLS, PAGE_ICON
from database import read_all_layer_snapshot, read_daily_trend, read_snapshot, read_locations, read_well_history
from helpers import filter_by_field, field_options, missing_coordinate_aliases
from maps import make_well_map
from metrics import calculate_daily_changes, calculate_kpis
from styles import inject_styles
from historical_uploader import render_wds_uploader


def calculate_well_alerts(current_df, previous_df):
    """Return actionable per-well alerts for the selected snapshot."""
    columns = ["Severity", "Alert", "Well", "Field", "Oil", "Gas", "Water", "Oil Change"]
    current = current_df.copy() if current_df is not None else pd.DataFrame()
    previous = previous_df.copy() if previous_df is not None else pd.DataFrame()

    for df in (current, previous):
        for column in ["ALIAS", "field", "OIL", "GAS", "WATER", "water_cut_pct"]:
            if column not in df.columns:
                df[column] = 0 if column not in ["ALIAS", "field"] else ""

    current = current.drop_duplicates(subset=["ALIAS"]).set_index("ALIAS", drop=False)
    previous = previous.drop_duplicates(subset=["ALIAS"]).set_index("ALIAS", drop=False)
    alerts = []

    for alias, row in current.iterrows():
        oil = float(row["OIL"] or 0)
        gas = float(row["GAS"] or 0)
        water = float(row["WATER"] or 0)
        water_cut = float(row["water_cut_pct"] or 0)
        prior_oil = float(previous.at[alias, "OIL"] or 0) if alias in previous.index else None
        prior_water_cut = float(previous.at[alias, "water_cut_pct"] or 0) if alias in previous.index else None
        oil_change = oil - prior_oil if prior_oil is not None else None
        base = {
            "Well": alias,
            "Field": row["field"],
            "Oil": round(oil, 1),
            "Gas": round(gas, 1),
            "Water": round(water, 1),
            "Oil Change": round(oil_change, 1) if oil_change is not None else None,
        }

        if prior_oil is not None and prior_oil > 0 and oil == 0:
            alerts.append({"Severity": "Warning", "Alert": "Zero oil production", **base})
        elif prior_oil is not None and prior_oil > 0 and (oil_change / prior_oil) <= -0.30:
            alerts.append({"Severity": "Critical", "Alert": "Oil dropped 30% or more", **base})

        if prior_water_cut is not None and (water_cut - prior_water_cut) > 1:
            alerts.append({"Severity": "Warning", "Alert": "Water cut increased by more than 1%", **base})

    for alias, row in previous.loc[~previous.index.isin(current.index)].iterrows():
        if float(row["OIL"] or 0) > 0:
            alerts.append({
                "Severity": "Watch",
                "Alert": "Missing from selected upload",
                "Well": alias,
                "Field": row["field"],
                "Oil": None,
                "Gas": None,
                "Water": None,
                "Oil Change": None,
            })

    if not alerts:
        return pd.DataFrame(columns=columns)
    severity_order = {"Critical": 0, "Warning": 1, "Watch": 2}
    return (
        pd.DataFrame(alerts)[columns]
        .assign(_order=lambda df: df["Severity"].map(severity_order))
        .sort_values(["_order", "Well", "Alert"])
        .drop(columns="_order")
        .reset_index(drop=True)
    )

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
    st.warning("No data yet in Supabase - add rows to the 'ProdWellBasiss' table to see the dashboard.")
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

render_wds_uploader()

display_wells = wells_df if selected_date_str == dates[0] else read_snapshot(selected_date_str)
filtered = filter_by_field(display_wells, field_filter)
reported_totals = pd.to_numeric(display_wells.get("reported_total"), errors="coerce").dropna()
reported_total = float(reported_totals.iloc[0]) if not reported_totals.empty else None
all_layer_wells = filter_by_field(read_all_layer_snapshot(selected_date_str), field_filter)
previous_date_str = (pd.Timestamp(selected_date) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
previous_all_layer_wells = filter_by_field(read_all_layer_snapshot(previous_date_str), field_filter)
well_alerts = calculate_well_alerts(all_layer_wells, previous_all_layer_wells)
kpis = calculate_kpis(filtered)
changes = calculate_daily_changes(trend_df, selected_date)
missing_aliases = missing_coordinate_aliases(display_wells)
if missing_aliases:
    st.warning("These wells have no saved coordinates: " + ", ".join(missing_aliases) + ". Add them to the 'HeaderID' table in Supabase.")

c1, c2, c3, c4, c5, c6 = st.columns(6)
reported_total_delta = (
    f"{changes['reported_total_change']:+,.0f} BOPD vs yesterday"
    if changes["reported_total_change"] is not None
    else None
)
c1.metric(
    "Total Production",
    f"{reported_total:,.0f} BOPD" if reported_total is not None else "Not uploaded",
    reported_total_delta,
)
c2.metric("Total Oil Production", f"{kpis['total_bopd']:,} BOPD", f"{changes['bopd_change']:+,} BOPD vs yesterday" if changes["bopd_change"] is not None else None)
gas_delta = f"{changes['gas_change']:+,.1f} MCF vs yesterday" if changes["gas_change"] is not None else None
c3.metric("Total Gas Production", f"{kpis['total_gas']:,.1f} MCF", gas_delta)
c4.metric("Total Water Production", f"{kpis['total_water_production']:,} BWPD", f"{changes['water_prod_change']:+,} BWPD vs yesterday" if changes["water_prod_change"] is not None else None)
c5.metric("Total Water Injection", f"{kpis['total_water_production']:,} BWPD", f"{changes['water_prod_change']:+,} BWPD vs yesterday" if changes["water_prod_change"] is not None else None)
c6.metric("Total Water Source", f"{kpis['total_water_source']:,} BWPD", f"{changes['water_source_change']:+,} BWPD vs yesterday" if changes["water_source_change"] is not None else None)

st.subheader("Well Alerts")
if well_alerts.empty:
    st.success("No well alerts for the selected date and field.")
else:
    st.dataframe(
        well_alerts,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Oil": st.column_config.NumberColumn("Oil (BOPD)", format="%.1f"),
            "Gas": st.column_config.NumberColumn("Gas (MCF)", format="%.1f"),
            "Water": st.column_config.NumberColumn("Water (BWPD)", format="%.1f"),
            "Oil Change": st.column_config.NumberColumn("Oil Change vs Yesterday", format="%+.1f"),
        },
    )

pie_col, map_col = st.columns([1, 1.3])
with pie_col:
    st.subheader("Status & Field Totals")
    st.plotly_chart(make_status_pie(all_layer_wells), use_container_width=True)
    st.plotly_chart(make_field_totals_bar(all_layer_wells), use_container_width=True)
with map_col:
    st.subheader("Well Map")
    st.plotly_chart(make_well_map(all_layer_wells), use_container_width=True)

st.subheader("Total Production Trend")
if trend_df.empty:
    st.caption("No history yet - upload data to see the trend.")
else:
    trend_agg = trend_df.copy()
    trend_agg["date"] = pd.to_datetime(trend_agg["date"])
    period = st.selectbox(
        "View period",
        ["Year to Date", "1 Year", "3 Years", "5 Years", "10 Years", "All Time"],
        key="total_production_trend_period",
    )
    latest_date = trend_agg["date"].max()
    if period == "Year to Date":
        start_date = latest_date.replace(month=1, day=1)
    elif period == "All Time":
        start_date = trend_agg["date"].min()
    else:
        start_date = latest_date - pd.DateOffset(years=int(period.split()[0]))
    trend_view = trend_agg[trend_agg["date"] >= start_date].copy()

    trend_view["bfpd"] = trend_view["OIL"] + trend_view["WATER"]
    denominator = trend_view["bfpd"].where(trend_view["bfpd"].ne(0))
    trend_view["water_cut_pct"] = (trend_view["WATER"] / denominator * 100).round(1).fillna(0.0)
    t1, t2, t3, t4, t5 = st.tabs(["BOPD", "BFPD", "BWPD", "Water Cut %", "Gas (MCF)"])
    with t1: st.plotly_chart(make_trend_fig(trend_view, "OIL", "#22c55e", "rgba(34,197,94,0.2)", "BOPD"), use_container_width=True)
    with t2: st.plotly_chart(make_trend_fig(trend_view, "bfpd", "#eab308", "rgba(234,179,9,0.2)", "BFPD"), use_container_width=True)
    with t3: st.plotly_chart(make_trend_fig(trend_view, "WATER", "#38bdf8", "rgba(56,189,248,0.2)", "BWPD"), use_container_width=True)
    with t4: st.plotly_chart(make_water_cut_trend_fig(trend_view), use_container_width=True)
    with t5: st.plotly_chart(make_trend_fig(trend_view, "GAS", "#f97316", "rgba(249,115,22,0.2)", "MCF"), use_container_width=True)

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
    metric_options = {
        "BOPD": ("OIL", "#22c55e", "rgba(34,197,94,0.2)", "BOPD"),
        "BFPD": ("bfpd", "#eab308", "rgba(234,179,9,0.2)", "BFPD"),
        "BWPD": ("WATER", "#38bdf8", "rgba(56,189,248,0.2)", "BWPD"),
        "Water Cut %": ("water_cut_pct", "#38bdf8", "rgba(56,189,248,0.15)", "Water Cut (%)"),
        "Gas (MCF)": ("GAS", "#f97316", "rgba(249,115,22,0.2)", "MCF"),
    }

    if not options:
        st.caption("No wells to display for this filter.")
    else:
        top_well = filtered.sort_values("OIL", ascending=False).iloc[0]["ALIAS"]
        if st.session_state.get("well_decline_selected_well") not in options:
            st.session_state["well_decline_selected_well"] = top_well
        if st.session_state.get("well_decline_metric") not in metric_options:
            st.session_state["well_decline_metric"] = "BOPD"

        selected_well = st.session_state["well_decline_selected_well"]
        selected_metric = st.session_state["well_decline_metric"]
        well_history = read_well_history(selected_well)

        if well_history.empty:
            st.caption(f"No history yet for {selected_well}.")
        else:
            y_col, line_color, fill_color, y_title = metric_options[selected_metric]
            st.plotly_chart(
                make_well_history_fig(well_history.sort_values("date"), y_col, line_color, fill_color, y_title),
                use_container_width=True,
            )

        st.selectbox("Select a well", options, key="well_decline_selected_well")
        st.radio(
            "Well decline metric",
            list(metric_options),
            key="well_decline_metric",
            horizontal=True,
            label_visibility="collapsed",
        )

st.subheader("Well Data")
table_cols = ["ALIAS", "field", "status", "OIL", "WATER", "bfpd", "water_cut_pct", "injection_rate"]
visible_cols = [c for c in table_cols if c in filtered.columns]
st.dataframe(filtered[visible_cols].sort_values("OIL", ascending=False), use_container_width=True, hide_index=True)