"""Separate Streamlit page for monthly production and lifting reconciliation."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from constants import APP_TITLE, PAGE_ICON
from monthly_reconciliation import (
    loss_segment_frame,
    make_loss_heatmap,
    make_monthly_trend_figure,
    make_rc_chart,
    make_sankey_figure,
    make_tank_transfer_figure,
    make_waterfall_figure,
    normalize_monthly_data,
    parse_lifting_workbook,
    read_monthly_reconciliation,
    reconciliation_components,
    upload_monthly_reconciliation,
)
from styles import inject_styles


st.set_page_config(
    page_title=f"Monthly Production & Lifting · {APP_TITLE}",
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_styles(st)

with st.sidebar:
    st.subheader("Navigation")
    st.page_link("app.py", label="Daily Production Dashboard", icon="🏠")
    st.page_link("pages/2_Monthly_Reconciliation.py", label="Monthly Reconciliation", icon="📊")
st.title("Monthly Production & Lifting")
st.caption(
    "Monthly reconciliation from the field through Block Stations, STA, Bajubang, Tempino, "
    "and official lifting received at KM-3 S. Gerong."
)

preview_df = pd.DataFrame()
with st.expander("Upload Monthly Lifting Recap", expanded=False):
    st.caption(
        "Upload the monthly recap workbook in .xls or .xlsx format. The page reads the yearly and RC sheets, "
        "shows a preview, and only writes to Supabase after confirmation."
    )
    uploaded = st.file_uploader(
        "Drop the monthly production and lifting workbook here",
        type=["xls", "xlsx"],
        key="monthly_lifting_uploader",
    )
    if uploaded is not None:
        try:
            with st.spinner("Reading monthly reconciliation data..."):
                preview_df, workbook_warnings = parse_lifting_workbook(uploaded)
            st.session_state["monthly_lifting_preview"] = preview_df
            actual_count = int(preview_df["reporting_status"].eq("Actual").sum())
            planned_count = int(preview_df["reporting_status"].eq("Planned").sum())
            c1, c2, c3 = st.columns(3)
            c1.metric("Months detected", f"{len(preview_df):,}")
            c2.metric("Actual months", f"{actual_count:,}")
            c3.metric("Planned/unreported", f"{planned_count:,}")
            if planned_count:
                st.info("Planned or unreported months are stored with their status and excluded from actual KPIs and loss trends.")
            for warning in workbook_warnings:
                st.warning(warning)
            display_columns = [
                "report_month",
                "reporting_status",
                "rc_bopd",
                "rc_volume_bbl",
                "field_production_bbl",
                "rc_pumping_net_bbl",
                "s_gerong_received_bbl",
            ]
            preview = preview_df[display_columns].copy()
            preview["report_month"] = preview["report_month"].dt.strftime("%b %Y")
            st.dataframe(
                preview,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "report_month": "Month",
                    "reporting_status": "Status",
                    "rc_bopd": st.column_config.NumberColumn("RC Actual (BOPD)", format="%.1f"),
                    "rc_volume_bbl": st.column_config.NumberColumn("RC Actual Volume", format="%.1f"),
                    "field_production_bbl": st.column_config.NumberColumn("Field Production", format="%.1f"),
                    "rc_pumping_net_bbl": st.column_config.NumberColumn("Pumping Net", format="%.1f"),
                    "s_gerong_received_bbl": st.column_config.NumberColumn("Received S. Gerong", format="%.1f"),
                },
            )
            confirmed = st.checkbox(
                "I reviewed the preview and want to update monthly reconciliation data.",
                key="confirm_monthly_lifting_upload",
            )
            if st.button(
                "Upload Monthly Reconciliation to Supabase",
                type="primary",
                disabled=not confirmed,
                key="upload_monthly_lifting_button",
            ):
                with st.spinner("Saving monthly reconciliation..."):
                    rows = upload_monthly_reconciliation(preview_df)
                st.success(f"Saved {rows:,} monthly reconciliation records.")
                st.cache_data.clear()
                st.rerun()
        except Exception as exc:
            st.error(f"The workbook could not be processed: {exc}")

try:
    stored_df = read_monthly_reconciliation()
    load_error = None
except Exception as exc:
    stored_df = pd.DataFrame()
    load_error = exc

if preview_df.empty:
    preview_df = st.session_state.get("monthly_lifting_preview", pd.DataFrame())

data = normalize_monthly_data(preview_df if not preview_df.empty else stored_df)
if data.empty:
    if load_error:
        st.warning(
            "Monthly reconciliation data is not available yet. Upload the first workbook to preview it, then save it "
            "after the Streamlit Supabase secret is available."
        )
    else:
        st.info("Upload the first monthly recap workbook to populate this page.")
    st.stop()

actual = data[data["reporting_status"].eq("Actual")].copy()
if actual.empty:
    st.info("The workbook contains no months marked as Actual yet.")
    st.stop()

year_options = sorted(actual["report_month"].dt.year.unique(), reverse=True)
filter_col, month_col = st.columns([1, 2])
with filter_col:
    selected_year = st.selectbox("Year", year_options, index=0)
year_data = actual[actual["report_month"].dt.year.eq(selected_year)]
month_options = list(year_data["report_month"].sort_values(ascending=False))
with month_col:
    selected_month = st.selectbox(
        "Reconciliation month",
        month_options,
        format_func=lambda value: pd.Timestamp(value).strftime("%B %Y"),
    )

selected = year_data[year_data["report_month"].eq(selected_month)].iloc[0]
field_production = float(selected["field_production_bbl"] or 0)
lifting = float(selected["s_gerong_received_bbl"] or 0)
gap = lifting - field_production
realization = lifting / field_production * 100 if field_production else 0.0
segments = loss_segment_frame(selected)
net_transfer_loss = float(segments["Signed Difference (bbl)"].sum())
loss_rows = segments[segments["Result"].eq("Loss")]
largest_loss = loss_rows.loc[loss_rows["Magnitude (bbl)"].idxmax()] if not loss_rows.empty else None

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Field Production", f"{field_production:,.1f} bbl")
with k2:
    st.metric("RC Actual Reference", f"{float(selected['rc_volume_bbl'] or 0):,.1f} bbl")
    st.caption(f"{float(selected['rc_bopd'] or 0):,.1f} BOPD")
k3.metric("Received S. Gerong", f"{lifting:,.1f} bbl")
k4.metric("Field-to-Lifting Gap", f"{gap:,.1f} bbl", f"{gap / field_production * 100:,.1f}%" if field_production else None, delta_color="normal")
k5.metric("Lifting Realization", f"{realization:,.1f}%")

if largest_loss is not None:
    st.caption(
        f"Largest transfer loss: {largest_loss['Segment']} — "
        f"{largest_loss['Magnitude (bbl)']:,.1f} bbl ({largest_loss['Magnitude (%)']:,.2f}%)."
    )

flow_tab, tank_tab, reconciliation_tab, trend_tab, losses_tab = st.tabs(
    ["Flow", "Tank Transfer", "Reconciliation", "Monthly Trends", "Losses"]
)
with flow_tab:
    st.plotly_chart(make_sankey_figure(selected), use_container_width=True, config={"displayModeBar": False})
    st.caption("Red branches indicate losses or inventory increases. Green branches indicate gains or inventory releases.")

with tank_tab:
    st.plotly_chart(make_tank_transfer_figure(selected), use_container_width=True, config={"displayModeBar": False})
    st.caption("Hover or tap each tank and shipping stage to view the transferred volume for the selected month.")

with reconciliation_tab:
    st.plotly_chart(make_waterfall_figure(selected), use_container_width=True, config={"displayModeBar": False})
    components = pd.DataFrame(reconciliation_components(selected), columns=["Component", "Impact (bbl)"])
    components["Classification"] = components["Impact (bbl)"].map(
        lambda value: "Loss / inventory increase" if value > 0 else "Gain / inventory release" if value < 0 else "Balanced"
    )
    st.dataframe(
        components,
        use_container_width=True,
        hide_index=True,
        column_config={"Impact (bbl)": st.column_config.NumberColumn(format="%.1f")},
    )

with trend_tab:
    st.plotly_chart(make_monthly_trend_figure(actual), use_container_width=True, config={"displayModeBar": False})
    st.plotly_chart(make_rc_chart(actual), use_container_width=True, config={"displayModeBar": False})

with losses_tab:
    loss_display = segments.copy()
    loss_display = loss_display.drop(columns=["Signed Difference (bbl)"])
    st.metric(
        "Net Transfer Loss" if net_transfer_loss >= 0 else "Net Transfer Gain",
        f"{abs(net_transfer_loss):,.1f} bbl",
    )
    st.dataframe(
        loss_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Sent (bbl)": st.column_config.NumberColumn(format="%.1f"),
            "Received (bbl)": st.column_config.NumberColumn(format="%.1f"),
            "Magnitude (bbl)": st.column_config.NumberColumn(format="%.1f"),
            "Magnitude (%)": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
    st.plotly_chart(make_loss_heatmap(actual), use_container_width=True, config={"displayModeBar": False})
    st.caption(
        "Positive values are shown as Loss. Negative values are shown as Gain. The field-to-lifting gap also includes "
        "stock movement and storage reconciliation, so it is not treated as transfer loss by itself."
    )

