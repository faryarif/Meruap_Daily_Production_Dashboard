"""Read-only 14-day management analysis. Missing observations are never zero-filled."""
from html import escape

import numpy as np
import pandas as pd


def period_stats(series):
    previous, current = series.iloc[:14].dropna(), series.iloc[14:].dropna()
    before, now = previous.mean(), current.mean()
    change = now - before
    complete = len(previous) == len(current) == 14
    return {
        "previous": before, "current": now, "change": change,
        "percent": change / before * 100 if pd.notna(before) and before > 0 else np.nan,
        "previous_days": len(previous), "current_days": len(current),
        "complete": complete,
        "shortfall": max(0.0, before * 14 - current.sum()) if complete else np.nan,
    }


def build_review(raw, trend, locations, selected_date, field="All"):
    requested = pd.Timestamp(selected_date).normalize()
    data = raw.copy()
    for col in ["date", "ALIAS", "UNIQUEID", "OIL", "WATER"]:
        if col not in data:
            data[col] = pd.Series(dtype="object")
    data["date"] = pd.to_datetime(data["date"], errors="coerce").dt.normalize()
    data = data[data["UNIQUEID"].astype(str).str.fullmatch(r"M-[0-9]{2}:AllLayer")].copy()
    data = data[data.date.between(requested - pd.Timedelta(days=55), requested)]
    for col in ["OIL", "WATER"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
        data.loc[~np.isfinite(data[col]) | (data[col] < 0), col] = np.nan
    warnings = []
    duplicate = data.duplicated(["date", "UNIQUEID"], keep=False)
    if duplicate.any():
        warnings.append("Duplicate well/date records excluded from numerical comparison.")
        data.loc[duplicate, ["OIL", "WATER"]] = np.nan
        data = data.drop_duplicates(["date", "UNIQUEID"])
    meta = locations.reindex(columns=["ALIAS", "field", "status"]).copy()
    ambiguous = meta.groupby("ALIAS")["field"].nunique().gt(1)
    if ambiguous.any():
        warnings.append("Conflicting field assignments excluded from field-specific reports.")
        meta.loc[meta.ALIAS.isin(ambiguous[ambiguous].index), "field"] = None
    meta = meta.drop_duplicates("ALIAS")
    data = data.merge(meta, on="ALIAS", how="left", validate="many_to_one")
    if field != "All":
        data = data[data.field.eq(field)].copy()
    # Coverage-based completeness is a conservative proxy, not an upload certification.
    recent = data[data.date >= requested - pd.Timedelta(days=27)]
    roster = recent.UNIQUEID.unique()
    if len(roster) == 0:
        raise ValueError("No AllLayer well observations in the selected field/date window.")
    coverage = recent.groupby("date").OIL.count()
    candidates = coverage[coverage.eq(len(roster))].index
    candidates = candidates[candidates >= requested - pd.Timedelta(days=13)]
    end = candidates.max() if len(candidates) else requested
    if end != requested:
        warnings.append(f"Review ends on {end:%d %b %Y}, the latest coverage-complete day at or before the selected date.")
    if not len(candidates):
        warnings.append("No coverage-complete endpoint found in the last 14 days; review is provisional.")
    dates = pd.date_range(end - pd.Timedelta(days=27), end, freq="D")
    data = data[data.date.isin(dates)].copy()
    roster = sorted(data.UNIQUEID.unique())
    oil = data.pivot(index="date", columns="UNIQUEID", values="OIL").reindex(index=dates, columns=roster)
    water = data.pivot(index="date", columns="UNIQUEID", values="WATER").reindex(index=dates, columns=roster)
    daily = pd.DataFrame(index=dates)
    daily.index.name = "date"
    daily["well_oil"] = oil.sum(axis=1, min_count=len(roster))
    daily["oil_wells_present"] = oil.count(axis=1)
    daily["ah2"] = np.nan
    if field == "All" and {"date", "reported_total"}.issubset(trend.columns):
        totals = trend[["date", "reported_total"]].copy()
        totals["date"] = pd.to_datetime(totals.date, errors="coerce").dt.normalize()
        totals["reported_total"] = pd.to_numeric(totals.reported_total, errors="coerce")
        totals.loc[~np.isfinite(totals.reported_total) | (totals.reported_total < 0), "reported_total"] = np.nan
        grouped = totals.groupby("date").reported_total
        daily["ah2"] = grouped.max().where(grouped.nunique().le(1)).reindex(dates)
    summary = {"Per-well oil (AllLayer)": period_stats(daily.well_oil)}
    if field == "All":
        summary = {"Total Production (AH2)": period_stats(daily.ah2), **summary}
    for label, stats in summary.items():
        if not stats["complete"]:
            warnings.append(f"{label}: {stats['previous_days']}/14 baseline days and {stats['current_days']}/14 current days. Available-day averages only; shortfall withheld.")
    rows = []
    metadata = data.sort_values("date").drop_duplicates("UNIQUEID", keep="last").set_index("UNIQUEID")
    for uid in roster:
        series, w = oil[uid], water[uid]
        before, now = series.iloc[:14], series.iloc[14:]
        complete = before.count() == now.count() == 14
        mean_before, mean_now = before.mean(), now.mean()
        delta = mean_now - mean_before if complete else np.nan
        fluid = series + w
        liquid_before, liquid_now = fluid.iloc[:14].mean(), fluid.iloc[14:].mean()
        wc_before = w.iloc[:14].sum() / fluid.iloc[:14].sum() * 100 if fluid.iloc[:14].count() == 14 and fluid.iloc[:14].sum() > 0 else np.nan
        wc_now = w.iloc[14:].sum() / fluid.iloc[14:].sum() * 100 if fluid.iloc[14:].count() == 14 and fluid.iloc[14:].sum() > 0 else np.nan
        wc_change = wc_now - wc_before
        became_zero = bool(complete and mean_before > 0 and now.iloc[-1] == 0)
        repeated = now.iloc[-7:].count() == 7 and now.iloc[-7:].nunique() == 1 and now.iloc[-1] > 0
        indication, action = "No decline", "Monitor"
        if not complete:
            indication, action = "Incomplete observations", "Verify missing records / upload"
        elif became_zero:
            indication, action = "Latest oil is zero", "Verify shutdown versus missing well test"
        elif delta < 0 and pd.notna(wc_change) and wc_change > 1:
            indication, action = "Oil down; water cut up >1 percentage point", "Verify well test and water production"
        elif delta < 0 and fluid.count() == 28 and liquid_now < liquid_before:
            indication, action = "Oil and liquid down", "Check runtime, pump and operating changes"
        elif delta < 0:
            indication, action = "Oil down; cause unconfirmed", "Review latest well test and operations"
        elif delta > 0:
            indication = "Oil increased"
        rows.append({
            "Well": uid.split(":")[0], "Field": metadata.loc[uid, "field"],
            "Status (current metadata)": metadata.loc[uid, "status"],
            "Previous BOPD": mean_before, "Current BOPD": mean_now,
            "Change BOPD": delta, "Change %": delta / mean_before * 100 if mean_before > 0 else np.nan,
            "WC change (pp)": wc_change, "Baseline days": int(before.count()), "Current days": int(now.count()),
            "Latest zero": became_zero, "Repeated last 7 days": bool(repeated),
            "Indication": indication, "Suggested action": action,
        })
    wells = pd.DataFrame(rows).sort_values("Change BOPD", na_position="last").reset_index(drop=True)
    if wells["Repeated last 7 days"].any():
        warnings.append("Some oil values repeat for 7 days. Verify well-test freshness; repeated values alone do not prove stale data.")
    warnings.append("Completeness uses the observed AllLayer roster, not an approved upload log. Source ETL zeros cannot be distinguished from true zero production; causes require operational confirmation.")
    return {"end": end, "start": dates[0], "current_start": dates[14], "field": field,
            "daily": daily, "summary": summary, "wells": wells, "warnings": warnings,
            "expected_wells": len(roster)}


def fmt(value, suffix=""):
    return "N/A" if pd.isna(value) else f"{value:,.1f}{suffix}"


def make_review_chart(review, basis, events=None):
    import plotly.graph_objects as go
    column = "ah2" if basis == "Total Production (AH2)" else "well_oil"
    series = review["daily"][column]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series.index, y=series, name="Daily oil", mode="lines", line=dict(color="#94a3b8", width=1), connectgaps=False))
    fig.add_trace(go.Scatter(x=series.index, y=series.rolling(7, min_periods=7).mean(), name="7-day average", line=dict(color="#22c55e", width=3), connectgaps=False))
    baseline = review["summary"][basis]["previous"]
    if pd.notna(baseline):
        fig.add_hline(y=float(baseline), line_dash="dash", line_color="#f59e0b", annotation_text="Previous 14-day average")
    fig.add_vrect(x0=review["current_start"].isoformat(), x1=review["end"].isoformat(), fillcolor="#ef4444", opacity=0.06, line_width=0)
    if events is not None:
        for _, event in events.iterrows():
            date = pd.to_datetime(event.get("Date"), errors="coerce")
            if pd.notna(date) and review["start"] <= date <= review["end"]:
                fig.add_vline(x=date.isoformat(), line_dash="dot", line_color="#a855f7")
                fig.add_annotation(x=date.isoformat(), y=1, yref="paper", text=escape(str(event.get("Event", "")))[:120], showarrow=False)
    fig.update_layout(height=310, margin=dict(l=0, r=0, t=25, b=0), paper_bgcolor="#0b1220", plot_bgcolor="#0b1220", font=dict(color="#94a3b8"), yaxis_title="Oil (BOPD)", hovermode="x unified", legend=dict(orientation="h"))
    return fig


def report_html(review, basis, actions, events):
    """Self-contained printable summary; escape all user-entered content."""
    stats = review["summary"][basis]
    series = review["daily"]["ah2" if basis == "Total Production (AH2)" else "well_oil"]
    valid = series.dropna()
    top = max(float(valid.max()) * 1.1, 1.0) if not valid.empty else 1.0
    def line(values, color, width):
        segments, points = [], []
        for i, value in enumerate(values):
            if pd.isna(value):
                if points:
                    segments.append(' '.join(points))
                    points = []
            else:
                points.append(f"{40+i*680/27:.1f},{165-float(value)*145/top:.1f}")
        if points:
            segments.append(' '.join(points))
        return ''.join(f'<polyline points="{p}" fill="none" stroke="{color}" stroke-width="{width}"/>' for p in segments)
    svg = '<svg viewBox="0 0 760 195" role="img" aria-label="28-day oil trend">'
    svg += f'<text x="0" y="15" font-size="11">{top:,.0f} BOPD</text><text x="18" y="166" font-size="11">0</text>'
    svg += line(series, '#94a3b8', 1.5) + line(series.rolling(7, min_periods=7).mean(), '#16a34a', 3)
    if pd.notna(stats['previous']):
        y = 165 - stats['previous'] * 145 / top
        svg += f'<line x1="40" x2="720" y1="{y:.1f}" y2="{y:.1f}" stroke="#d97706" stroke-dasharray="5 4"/>'
    svg += f'<text x="40" y="190" font-size="12">{review["start"]:%d %b}</text><text x="650" y="190" font-size="12">{review["end"]:%d %b %Y}</text></svg>'
    top_wells = review["wells"].loc[review["wells"]["Change BOPD"] < 0].head(10)
    columns = ["Well", "Previous BOPD", "Current BOPD", "Change BOPD", "WC change (pp)"]
    summary_rows = [{"Basis": label, "Previous BOPD": s["previous"], "Current BOPD": s["current"], "Change %": s["percent"], "Days (previous/current)": f'{s["previous_days"]}/14; {s["current_days"]}/14'} for label, s in review["summary"].items()]
    def table(frame):
        return frame.to_html(index=False, escape=True, border=0, na_rep="N/A", float_format=lambda v: f"{v:,.1f}")
    warnings = ''.join(f'<li>{escape(w)}</li>' for w in review['warnings'])
    deltas = review['wells']['Change BOPD'].dropna()
    reconciliation = f"Comparable wells: {len(deltas)}/{len(review['wells'])}; declines {deltas[deltas<0].sum():,.1f} BOPD; gains +{deltas[deltas>0].sum():,.1f} BOPD; net {deltas.sum():+,.1f} BOPD."
    quality_label = "Complete 14 + 14 calendar-day coverage" if stats['complete'] else "PROVISIONAL — incomplete coverage; available-day averages only"
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>Oil Production Review</title>
    <style>body{{font:13px Arial,sans-serif;color:#17243b;max-width:1000px;margin:24px auto}}h1{{font-size:24px}}h2{{font-size:16px}}table{{border-collapse:collapse;width:100%;font-size:11px}}td,th{{padding:5px;border-bottom:1px solid #ddd;text-align:left;overflow-wrap:anywhere}}.metrics{{display:flex;gap:25px;margin:15px 0}}.metrics b{{display:block;font-size:22px}}.notes{{font-size:10px}}svg{{width:100%;max-height:210px}}@media print{{@page{{size:A4 landscape;margin:12mm}}body{{margin:0;font-size:10px}}h1{{font-size:18px;margin:0 0 8px}}h2{{font-size:12px;margin:8px 0}}td,th{{padding:3px;font-size:9px}}.metrics{{margin:8px 0}}.metrics b{{font-size:16px}}svg{{max-height:120px}}.notes{{font-size:9px}}.appendix{{break-before:page}}}}</style></head><body>
    <h1>Oil Production Decline — 14-Day Review</h1>
    <strong>{quality_label}</strong>
    <p>Scope: {escape(str(review['field']))} | Basis: {escape(basis)}<br>
    Baseline {review['start']:%d %b %Y} – {review['current_start']-pd.Timedelta(days=1):%d %b %Y}; current {review['current_start']:%d %b %Y} – {review['end']:%d %b %Y}</p>
    <div class="metrics"><div>Current average<b>{fmt(stats['current'])} BOPD</b></div><div>Change<b>{fmt(stats['change'])} BOPD ({fmt(stats['percent'])}%)</b></div><div>Shortfall vs baseline<b>{fmt(stats['shortfall'])} bbl</b></div></div>
    {table(pd.DataFrame(summary_rows))}
    <h2>28-day oil trend</h2>{svg}<small>Grey: daily oil; green: 7-day average; orange: previous-period average. Missing dates are gaps.</small>
    <h2>Top decline contributors — AllLayer well oil, not AH2 allocation</h2><small>{reconciliation}</small>{table(top_wells[columns])}
    <ul class="notes">{warnings}</ul>
    <div class="appendix"><h2>Actions and operational events</h2><p>Manually entered; causes are not inferred as confirmed. Session-only notes exported with this report.</p>{table(actions)}<h2>Events</h2>{table(events)}</div>
    </body></html>'''


def render_decline_review(trend, locations, selected_date, field):
    import streamlit as st
    import plotly.express as px
    from database import read_decline_window

    one_decimal = lambda columns: {
        column: st.column_config.NumberColumn(format="%.1f")
        for column in columns
    }
    st.subheader("Oil Production Decline — 14-Day Review")
    enabled = st.checkbox("Show management review", value=False, key="show_oil_management_review")
    if not enabled:
        st.caption("Compare the latest 14 days with the preceding 14 days; load the review on demand.")
        return
    try:
        with st.spinner("Preparing the management review..."):
            review = build_review(read_decline_window(selected_date), trend, locations, selected_date, field)
    except Exception as exc:
        st.warning(f"Management review unavailable: {exc}")
        return
    st.caption(f"Baseline: {review['start']:%d %b %Y}–{review['current_start']-pd.Timedelta(days=1):%d %b %Y} | Current: {review['current_start']:%d %b %Y}–{review['end']:%d %b %Y} | Field: {field}")
    basis = st.radio("Management reporting basis", list(review["summary"]), horizontal=True, key=f"review_basis_{field}")
    if field != "All":
        st.caption("AH2 is a whole-field reported total and is not allocated to individual fields. This view uses AllLayer well oil only.")
    stats = review["summary"][basis]
    if not stats["complete"]:
        st.warning("PROVISIONAL: incomplete calendar-day coverage. Averages use available valid days; no volume shortfall is estimated.")
    a, b, c, d = st.columns(4)
    a.metric("14-day average oil", fmt(stats["current"], " BOPD"))
    b.metric("Change vs prior period", fmt(stats["change"], " BOPD"), fmt(stats["percent"], "%"))
    c.metric("Shortfall vs baseline", fmt(stats["shortfall"], " bbl"))
    wells = review["wells"]
    d.metric("Wells with lower oil", str(int((wells["Change BOPD"] < 0).sum())), f"{int(wells['Latest zero'].sum())} now zero", delta_color="off")
    st.caption(f"Coverage: {stats['previous_days']}/14 baseline days; {stats['current_days']}/14 current days. Shortfall is a baseline comparison, not confirmed recoverable production.")
    summary = pd.DataFrame([{"Basis": label, "Previous BOPD": s["previous"], "Current BOPD": s["current"], "Change BOPD": s["change"], "Baseline days": s["previous_days"], "Current days": s["current_days"]} for label, s in review["summary"].items()])
    st.dataframe(
        summary,
        hide_index=True,
        use_container_width=True,
        column_config={
            **one_decimal(["Previous BOPD", "Current BOPD", "Change BOPD"]),
            **{
                "Baseline days": st.column_config.NumberColumn(format="%d"),
                "Current days": st.column_config.NumberColumn(format="%d"),
            },
        },
    )
    scope = f"{field}_{review['end']:%Y%m%d}"
    with st.expander("Operational events — optional"):
        st.caption("Enter confirmed events only. Notes stay in this browser session; download the report to retain them.")
        events = st.data_editor(pd.DataFrame({"Date": pd.Series(dtype="datetime64[ns]"), "Event": pd.Series(dtype="str")}), num_rows="dynamic", key=f"review_events_{scope}", use_container_width=True)
    st.plotly_chart(make_review_chart(review, basis, events), use_container_width=True)
    st.markdown("#### Top 10 Oil Decline Contributors")
    declined = wells[wells["Change BOPD"] < 0].head(10).sort_values("Change BOPD", ascending=False)
    if declined.empty:
        st.info("No comparable wells show a decline, or observations are incomplete.")
    else:
        fig = px.bar(declined, x="Change BOPD", y="Well", orientation="h", color_discrete_sequence=["#ef4444"])
        fig.update_traces(hovertemplate="Well=%{y}<br>Change BOPD=%{x:,.1f}<extra></extra>")
        fig.update_layout(
            height=330,
            margin=dict(l=0, r=0, t=10, b=0),
            xaxis=dict(title="Change in average oil (BOPD)", tickformat=",.1f"),
        )
        st.plotly_chart(fig, use_container_width=True)
    deltas = wells["Change BOPD"].dropna()
    if not deltas.empty:
        st.caption(f"Comparable wells ({len(deltas)}/{len(wells)}): declines {deltas[deltas<0].sum():,.1f} BOPD; gains +{deltas[deltas>0].sum():,.1f} BOPD; net {deltas.sum():+,.1f} BOPD. Well contributions explain AllLayer oil, not an allocation of AH2.")
    st.dataframe(
        wells,
        hide_index=True,
        use_container_width=True,
        column_config=one_decimal([
            "Previous BOPD",
            "Current BOPD",
            "Change BOPD",
            "Change %",
            "WC change (pp)",
        ]),
    )
    with st.expander("Action register"):
        st.caption("Session-only working notes, not shared or saved to the database. Include them in the downloaded report.")
        action_rows = wells.loc[(wells["Change BOPD"] < 0) | wells["Change BOPD"].isna(), ["Well", "Indication", "Suggested action"]].copy()
        for column in ["Confirmed cause", "PIC", "Action", "Target date", "Progress"]:
            action_rows[column] = ""
        actions = st.data_editor(action_rows, disabled=["Well", "Indication", "Suggested action"], key=f"review_actions_{scope}", hide_index=True, use_container_width=True)
    with st.expander("Data quality and calculation notes"):
        for warning in review["warnings"]:
            st.write("• " + warning)
        st.write("Water-cut changes use volume-weighted water cut and are expressed in percentage points. Per-well changes require 14 valid oil observations in each period. Current metadata status is not historical operating status.")
        st.dataframe(
            review["daily"].reset_index(),
            hide_index=True,
            use_container_width=True,
            column_config={
                **one_decimal(["well_oil", "ah2"]),
                "oil_wells_present": st.column_config.NumberColumn(format="%d"),
            },
        )
    st.download_button("Download Management Report", data=report_html(review, basis, actions, events), file_name=f"oil_review_{review['end']:%Y%m%d}.html", mime="text/html", key=f"download_review_{scope}")
    st.caption("Download a self-contained HTML report. Open it in a browser and Print → Save as PDF; the action register is an appendix.")

