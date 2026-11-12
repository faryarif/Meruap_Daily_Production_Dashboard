"""Ranked, responsive oil-production standings for the dashboard."""
from html import escape
from math import isfinite

import pandas as pd
import streamlit as st


STATUS_COLORS = {
    "Oil": "#22c55e",
    "Injector": "#3b82f6",
    "Water Source": "#1e3a8a",
    "Shut-in": "#eab308",
    "Down": "#6b7280",
    "Plug Abandon": "#ef4444",
}


def _display(value):
    if value is None or pd.isna(value):
        return "—"
    return escape(str(value), quote=True)


def _number(value):
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(parsed) or not isfinite(float(parsed)):
        return None
    return float(parsed)


def render_well_standings(wells, report_date=None, field="All"):
    """Render all selected wells in descending oil-rate order."""
    st.subheader("Well Data")
    if wells is None or wells.empty:
        st.info("No well records are available for this report date and field.")
        return

    ranked = wells.copy()
    if "OIL" not in ranked.columns:
        ranked["OIL"] = 0
    ranked["OIL"] = pd.to_numeric(ranked["OIL"], errors="coerce")
    ranked = ranked.sort_values(
        "OIL", ascending=False, na_position="last", kind="mergesort"
    ).reset_index(drop=True)
    ranked.insert(0, "Rank", range(1, len(ranked) + 1))

    caption_parts = []
    if report_date:
        caption_parts.append(f"Report Date: {report_date}")
    caption_parts.append(f"Field: {field}")
    st.caption(" · ".join(caption_parts) + " · Ranked by oil production, highest first.")

    optional_metrics = [
        ("GAS", "Gas (MCF)"),
        ("WATER", "Water (BWPD)"),
        ("bfpd", "BFPD"),
        ("water_cut_pct", "Water Cut"),
        ("injection_rate", "Injection (BWPD)"),
    ]
    available_metrics = [
        (column, label) for column, label in optional_metrics
        if column in ranked.columns
    ]

    max_oil = max(
        (_number(value) or 0.0 for value in ranked["OIL"]),
        default=0.0,
    )
    rows = []
    for _, row in ranked.iterrows():
        rank = int(row["Rank"])
        oil = _number(row.get("OIL"))
        bar_width = min(100.0, max(0.0, oil / max_oil * 100.0)) if oil and max_oil else 0.0
        if rank == 1:
            badge = "🏆 <span>1</span>"
            rank_class = "rank-first"
            lead = '<span class="leader-tag">TOP OIL PRODUCER</span>'
        elif rank == 2:
            badge = "🥈 <span>2</span>"
            rank_class = "rank-second"
            lead = ""
        elif rank == 3:
            badge = "🥉 <span>3</span>"
            rank_class = "rank-third"
            lead = ""
        else:
            badge = f'<span class="plain-rank">{rank}</span>'
            rank_class = ""
            lead = ""

        status = str(row.get("status", "Unknown"))
        status_color = STATUS_COLORS.get(status, "#64748b")
        cells = [
            f'<td class="rank-cell"><span class="rank-badge {rank_class}">{badge}</span></td>',
            (
                '<td class="well-cell">'
                f'<strong>{_display(row.get("ALIAS"))}</strong>{lead}</td>'
            ),
            f'<td>{_display(row.get("field"))}</td>',
            (
                '<td><span class="status-pill" '
                f'style="--status-color:{status_color}">{_display(status)}</span></td>'
            ),
            (
                '<td class="oil-cell">'
                f'<strong>{f"{oil:,.1f}" if oil is not None else "—"}</strong>'
                '<span class="oil-unit">BOPD</span></td>'
            ),
            (
                '<td class="bar-cell"><div class="oil-track">'
                f'<span style="width:{bar_width:.1f}%"></span></div></td>'
            ),
        ]
        for column, _label in available_metrics:
            value = _number(row.get(column))
            formatted = f"{value:,.1f}" if value is not None else "—"
            if column == "water_cut_pct" and value is not None:
                formatted += "%"
            cells.append(f'<td class="numeric-cell">{formatted}</td>')
        rows.append(f'<tr class="{rank_class}">{"".join(cells)}</tr>')

    headings = [
        "<th class=\"rank-head\">#</th>",
        "<th>Well</th>",
        "<th>Field</th>",
        "<th>Status</th>",
        "<th>Oil production</th>",
        "<th class=\"bar-head\"></th>",
    ]
    headings.extend(f"<th>{escape(label)}</th>" for _column, label in available_metrics)
    table_html = f"""
    <style>
    .well-standings-shell {{
        overflow-x: auto; border: 1px solid #263144; border-radius: 14px;
        background: #0d1728; box-shadow: 0 10px 30px rgba(0,0,0,.18);
        -webkit-overflow-scrolling: touch;
    }}
    .well-standings {{
        width: 100%; min-width: 900px; border-collapse: separate;
        border-spacing: 0; color: #dbe6f4; font-size: .9rem;
    }}
    .well-standings th {{
        position: sticky; top: 0; z-index: 1; padding: 12px 14px;
        background: #17243a; color: #9fb2ca; text-align: left;
        font-size: .72rem; letter-spacing: .06em; text-transform: uppercase;
        border-bottom: 1px solid #2b3b53; white-space: nowrap;
    }}
    .well-standings td {{
        padding: 11px 14px; border-bottom: 1px solid rgba(71,85,105,.25);
        white-space: nowrap;
    }}
    .well-standings tbody tr:last-child td {{ border-bottom: 0; }}
    .well-standings tbody tr:hover {{ background: rgba(56,189,248,.07); }}
    .well-standings tbody tr.rank-first {{
        background: linear-gradient(90deg, rgba(34,197,94,.16), rgba(34,197,94,.035));
    }}
    .well-standings tbody tr.rank-second {{ background: rgba(148,163,184,.055); }}
    .well-standings tbody tr.rank-third {{ background: rgba(217,119,6,.055); }}
    .rank-cell {{ width: 66px; }}
    .rank-badge {{ display: inline-flex; align-items: center; gap: 5px; font-weight: 800; }}
    .rank-first .rank-badge {{ color: #86efac; }}
    .rank-second .rank-badge {{ color: #cbd5e1; }}
    .rank-third .rank-badge {{ color: #fdba74; }}
    .plain-rank {{ display: inline-flex; min-width: 24px; justify-content: center; color: #8da0b8; font-weight: 700; }}
    .well-cell strong {{ color: #f1f5f9; font-size: .96rem; }}
    .leader-tag {{
        display: inline-block; margin-left: 8px; padding: 3px 6px;
        border: 1px solid rgba(34,197,94,.35); border-radius: 999px;
        color: #86efac; font-size: .58rem; letter-spacing: .04em;
        vertical-align: middle;
    }}
    .status-pill {{
        display: inline-block; padding: 3px 8px; border-radius: 999px;
        background: color-mix(in srgb, var(--status-color) 16%, transparent);
        color: var(--status-color); border: 1px solid color-mix(in srgb, var(--status-color) 35%, transparent);
        font-size: .76rem; font-weight: 650;
    }}
    .oil-cell strong {{ color: #f8fafc; font-variant-numeric: tabular-nums; }}
    .oil-unit {{ margin-left: 5px; color: #8193aa; font-size: .7rem; }}
    .bar-head {{ min-width: 120px; }}
    .bar-cell {{ min-width: 120px; }}
    .oil-track {{ height: 7px; width: 100%; overflow: hidden; border-radius: 999px; background: #243247; }}
    .oil-track span {{ display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg,#16a34a,#4ade80); }}
    .numeric-cell {{ text-align: right; font-variant-numeric: tabular-nums; }}
    @media (max-width: 640px) {{
        .well-standings {{ min-width: 850px; font-size: .82rem; }}
        .well-standings th, .well-standings td {{ padding: 10px 11px; }}
        .leader-tag {{ display: none; }}
    }}
    </style>
    <div class="well-standings-shell">
      <table class="well-standings" aria-label="Well oil production standings">
        <thead><tr>{"".join(headings)}</tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)
