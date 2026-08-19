import plotly.express as px
import plotly.graph_objects as go

from constants import STATUS_COLORS
from helpers import order_field_totals


def apply_dark_layout(fig, height, font_color="#94a3b8"):
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="#0b1220", plot_bgcolor="#0b1220", font=dict(color=font_color))
    return fig


def make_status_pie(filtered_df):
    status_counts = filtered_df["status"].value_counts().reset_index(); status_counts.columns = ["status", "count"]
    fig = px.pie(status_counts, names="status", values="count", color="status", color_discrete_map=STATUS_COLORS, hole=0.55)
    fig.update_traces(texttemplate="%{label}: %{value}", textposition="outside", hovertemplate="%{label}: %{value} wells<extra></extra>")
    apply_dark_layout(fig, 200, "#e2e8f0"); fig.update_layout(legend=dict(font=dict(color="#e2e8f0"), orientation="h")); return fig


def make_field_totals_bar(display_wells):
    field_totals = order_field_totals(display_wells.groupby("field", dropna=False)["OIL"].sum().reset_index())
    fig = px.bar(field_totals, x="OIL", y="field", orientation="h", color_discrete_sequence=["#38bdf8"])
    apply_dark_layout(fig, 200); fig.update_layout(xaxis_title=None, yaxis_title=None, yaxis=dict(categoryorder="array", categoryarray=field_totals["field"].tolist()[::-1])); return fig


def make_trend_fig(trend_agg, y_col, line_color, fill_color, y_title, markers=False):
    fig = go.Figure(); fig.add_trace(go.Scatter(x=trend_agg["date"], y=trend_agg[y_col], mode="lines+markers" if markers else "lines", fill="tozeroy", line=dict(color=line_color, width=2), fillcolor=fill_color))
    apply_dark_layout(fig, 280); fig.update_layout(xaxis=dict(gridcolor="#263144"), yaxis=dict(gridcolor="#263144", title=y_title)); return fig


def make_water_cut_trend_fig(trend_agg):
    fig = make_trend_fig(trend_agg, "water_cut_pct", "#38bdf8", "rgba(56,189,248,0.15)", "Water Cut (%)", markers=False)
    fig.update_layout(yaxis=dict(gridcolor="#263144", title="Water Cut (%)", range=[0, 100])); return fig


def make_injection_trend_fig(inj_by_date):
    fig = px.line(inj_by_date, x="date", y="injection_rate", color="status", color_discrete_map={"Injector": "#f59e0b", "Water Source": "#a855f7"}, markers=False)
    apply_dark_layout(fig, 280); fig.update_layout(xaxis=dict(gridcolor="#263144"), yaxis=dict(gridcolor="#263144", title="Injection Rate"), legend=dict(font=dict(color="#e2e8f0"), orientation="h")); return fig


def make_top_wells_bar(filtered_df):
    top_wells = filtered_df.sort_values("OIL", ascending=False).head(8)
    fig = px.bar(top_wells, x="ALIAS", y="OIL", color_discrete_sequence=["#38bdf8"])
    apply_dark_layout(fig, 300); fig.update_layout(xaxis_title=None, yaxis_title="BOPD"); return fig


def make_well_history_fig(well_history, y_col, line_color, fill_color, y_title):
    # Match the corresponding Total Production Trend colors, and keep all Well Decline Trend series clean.
    trend_colors = {"OIL": ("#22c55e", "rgba(34,197,94,0.2)"), "bfpd": ("#eab308", "rgba(234,179,9,0.2)"), "WATER": ("#38bdf8", "rgba(56,189,248,0.2)"), "water_cut_pct": ("#38bdf8", "rgba(56,189,248,0.15)")}
    line_color, fill_color = trend_colors.get(y_col, (line_color, fill_color))
    fig = go.Figure(); fig.add_trace(go.Scatter(x=well_history["date"], y=well_history[y_col], mode="lines", fill="tozeroy", line=dict(color=line_color, width=2), fillcolor=fill_color))
    apply_dark_layout(fig, 300); fig.update_layout(xaxis=dict(gridcolor="#263144"), yaxis=dict(gridcolor="#263144", title=y_title))
    if y_col == "water_cut_pct": fig.update_layout(yaxis=dict(gridcolor="#263144", title=y_title, range=[0, 100]))
    return fig
