"""
Daily Production & Well Map Dashboard - Shared via Supabase
------------------------------------------------------------------
Run locally:
    streamlit run app.py

Supabase tables needed:
    - ProdWellBasiss : id, date, ALIAS, OIL, WATER, injection_rate
    - HeaderID       : ALIAS, field, status, latitude, longitude

Streamlit secrets (.streamlit/secrets.toml):
    [supabase]
    url = "https://xxxx.supabase.co"
    key = "your-anon-public-key"
"""

from datetime import datetime

import pandas as pd
import streamlit as st

from charts import (
    make_field_totals_bar,
    make_injection_trend_fig,
    make_status_pie,
    make_top_wells_bar,
    make_trend_fig,
    make_water_cut_trend_fig,
    make_well_history_fig,
)
from constants import APP_TITLE, DATA_PROD_COLS, LOCATION_HEAD_COLS, PAGE_ICON
from database import read_data, read_locations
from helpers import (
    available_dates,
    field_options,
    filter_by_field,
    missing_coordinate_aliases,
    prepare_dashboard_frames,
    snapshot_for_date,
)
from maps import make_well_map
from metrics import aggregate_injection_trend, aggregate_production_trend, calculate_daily_changes, calculate_kpis
from styles import inject_styles


st.set_page_config(
    page_title=APP_TITLE,
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_styles(st)


try:
    raw_wells_df, raw_history_df = read_data()
    locations_df = read_locations()
    wells_df, history_df, locations_df = prepare_dashboard_frames(
        raw_wells_df,
        raw_history_df,
        locations_df,
    )
except Exception as exc:
    st.error(f"Couldn't connect to Supabase - check your secrets configuration. Details: {exc}")
    wells_df = None
    history_df = pd.DataFrame(columns=DATA_PROD_COLS)
    locations_df = pd.DataFrame(columns=LOCATION_HEAD_COLS)

if wells_df is None or wells_df.empty:
    st.warning("No data yet in Supabase - add rows to the 'ProdWellBasiss' table to see the dashboard.")
    st.stop()

missing_aliases = missing_coordinate_aliases(wells_df)
if missing_aliases:
    st.warning(
        "These wells have no saved coordinates: "
        + ", ".join(missing_aliases)
        + ". Add them to the 'HeaderID' table in Supabase."
    )


col_title, col_date, col_filter = st.columns([3, 1, 1])
with col_title:
    st.title("Daily Production Dashboard")
    st.caption("· Shared live dashboard · " + datetime.now().strftime("%A, %B %d, %Y"))

with col_date:
    dates = available_dates(history_df)
    if dates:
        date_values = [datetime.strptime(date, "%Y-%m-%d").date() for date in dates]
        selected_date = st.date_input(
            "Snapshot date",
            value=date_values[0],
            min_value=date_values[-1],
            max_value=date_values[0],
        )
        selected_date_str = selected_date.strftime("%Y-%m-%d")
    else:
        selected_date_str = None

with col_filter:
    field_filter = st.selectbox("Field", field_options(wells_df))

display_wells = snapshot_for_date(history_df, locations_df, selected_date_str, wells_df)
filtered = filter_by_field(display_wells, field_filter)
kpis = calculate_kpis(filtered)
changes = calculate_daily_changes(history_df)


row1_c1, row1_c2, row1_c3, row1_c4 = st.columns(4)
row1_c1.metric(
    "Total Production",
    f"{kpis['total_bopd']:,} BOPD",
    f"{changes['bopd_change']:+,} BOPD vs yesterday" if changes["bopd_change"] is not None else None,
)
row1_c2.metric(
    "Total Injection",
    f"{kpis['total_injection']:,} Barrels",
    f"{changes['injection_change']:+,} Barrels vs yesterday"
    if changes["injection_change"] is not None
    else None,
)
row1_c3.metric(
    "Total Water Production",
    f"{kpis['total_water_production']:,} BWPD",
    f"{changes['water_prod_change']:+,} BWPD vs yesterday"
    if changes["water_prod_change"] is not None
    else None,
)
row1_c4.metric(
    "Total Water Source",
    f"{kpis['total_water_source']:,} BWPD",
    f"{changes['water_source_change']:+,} BWPD vs yesterday"
    if changes["water_source_change"] is not None
    else None,
)

st.markdown("")


pie_col, map_col = st.columns([1, 1.3])

with pie_col:
    st.subheader("Status & Field Totals")
    st.plotly_chart(make_status_pie(filtered), use_container_width=True)
    st.plotly_chart(make_field_totals_bar(display_wells), use_container_width=True)

with map_col:
    st.subheader("Well Map")
    st.plotly_chart(make_well_map(filtered), use_container_width=True)


st.subheader("Total Production Trend")
trend_agg = aggregate_production_trend(history_df)
if trend_agg.empty:
    st.caption("No history yet - upload data to see the trend.")
else:
    trend_tab1, trend_tab2, trend_tab3, trend_tab4 = st.tabs(["BOPD", "BFPD", "BWPD", "Water Cut %"])

    with trend_tab1:
        st.plotly_chart(
            make_trend_fig(trend_agg, "OIL", "#22c55e", "rgba(34,197,94,0.2)", "BOPD"),
            use_container_width=True,
        )
    with trend_tab2:
        st.plotly_chart(
            make_trend_fig(trend_agg, "bfpd", "#eab308", "rgba(234,179,8,0.2)", "BFPD"),
            use_container_width=True,
        )
    with trend_tab3:
        st.plotly_chart(
            make_trend_fig(trend_agg, "WATER", "#38bdf8", "rgba(56,189,248,0.2)", "BWPD"),
            use_container_width=True,
        )
    with trend_tab4:
        st.plotly_chart(make_water_cut_trend_fig(trend_agg), use_container_width=True)


st.subheader("Injection Rate Trend")
inj_by_date = aggregate_injection_trend(history_df)
if history_df.empty:
    st.caption("No history yet - upload data to see the trend.")
elif inj_by_date.empty:
    st.caption("No Injector or Water Source wells found in data yet.")
else:
    st.plotly_chart(make_injection_trend_fig(inj_by_date), use_container_width=True)


top_col, detail_col = st.columns(2)

with top_col:
    st.subheader("Top Producing Wells")
    st.plotly_chart(make_top_wells_bar(filtered), use_container_width=True)

with detail_col:
    st.subheader("Well Decline Trend")
    well_options = filtered["ALIAS"].tolist()
    if not well_options:
        st.caption("No wells to display for this filter.")
        selected_well = None
    else:
        top_well = filtered.sort_values("OIL", ascending=False).iloc[0]["ALIAS"]
        selected_well = st.selectbox(
            "Select a well",
            well_options,
            index=well_options.index(top_well),
        )

    well_history = (
        history_df[history_df["ALIAS"] == selected_well].sort_values("date").copy()
        if selected_well and not history_df.empty
        else pd.DataFrame()
    )
    if well_history.empty:
        if selected_well:
            st.caption(f"No history yet for {selected_well}.")
    else:
        w_tab1, w_tab2, w_tab3, w_tab4 = st.tabs(["BOPD", "BFPD", "BWPD", "Water Cut %"])
        with w_tab1:
            st.plotly_chart(
                make_well_history_fig(well_history, "OIL", "#22c55e", "rgba(34,197,94,0.2)", "BOPD"),
                use_container_width=True,
            )
        with w_tab2:
            st.plotly_chart(
                make_well_history_fig(well_history, "bfpd", "#eab308", "rgba(234,179,8,0.2)", "BFPD"),
                use_container_width=True,
            )
        with w_tab3:
            st.plotly_chart(
                make_well_history_fig(well_history, "WATER", "#38bdf8", "rgba(56,189,248,0.2)", "BWPD"),
                use_container_width=True,
            )
        with w_tab4:
            st.plotly_chart(
                make_well_history_fig(
                    well_history,
                    "water_cut_pct",
                    "#ef4444",
                    "rgba(239,68,68,0.15)",
                    "Water Cut (%)",
                ),
                use_container_width=True,
            )


st.subheader("Well Data")
table_cols = [
    "ALIAS",
    "field",
    "status",
    "OIL",
    "WATER",
    "bfpd",
    "water_cut_pct",
    "injection_rate",
    "latitude",
    "longitude",
]
visible_cols = [col for col in table_cols if col in filtered.columns]
st.dataframe(
    filtered[visible_cols].sort_values("OIL", ascending=False),
    use_container_width=True,
    hide_index=True,
)
