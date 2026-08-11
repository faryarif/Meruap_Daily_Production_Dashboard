import pandas as pd


def calculate_kpis(filtered_df):
    return {
        "total_bopd": int(filtered_df["OIL"].sum()),
        "active_count": int((filtered_df["status"] == "Oil").sum()),
        "shutin_count": int((filtered_df["status"] == "Shut-in").sum()),
        "down_count": int((filtered_df["status"] == "Down").sum()),
        "injector_count": int((filtered_df["status"] == "Injector").sum()),
        "water_source_count": int((filtered_df["status"] == "Water Source").sum()),
        "total_injection": int(filtered_df.loc[filtered_df["status"] == "Injector", "injection_rate"].sum()),
        "total_water_source": int(filtered_df.loc[filtered_df["status"] == "Water Source", "WATER"].sum()),
        "total_water_production": int(filtered_df["WATER"].sum()),
    }


def calculate_daily_changes(trend_df, selected_date=None):
    changes = {
        "bopd_change": None,
        "injection_change": None,
        "water_prod_change": None,
        "water_source_change": None,
    }
    if trend_df is None or trend_df.empty or "date" not in trend_df.columns:
        return changes

    trend = trend_df.copy()
    trend["date"] = pd.to_datetime(trend["date"], errors="coerce").dt.normalize()
    trend = trend.dropna(subset=["date"])

    if selected_date is None:
        selected = trend["date"].max()
    else:
        selected = pd.Timestamp(selected_date).normalize()

    # "Yesterday" means the actual calendar day immediately before the
    # selected dashboard date, not the previous available production record.
    yesterday = selected - pd.Timedelta(days=1)

    current_rows = trend.loc[trend["date"] == selected]
    previous_rows = trend.loc[trend["date"] == yesterday]

    # If the exact calendar day has no production record, do not silently
    # compare against an older available record. Show no comparison instead.
    if current_rows.empty or previous_rows.empty:
        return changes

    curr = current_rows.iloc[0]
    prev = previous_rows.iloc[0]
    changes["bopd_change"] = int(curr.get("OIL", 0)) - int(prev.get("OIL", 0))
    changes["injection_change"] = int(curr.get("injection_rate", 0)) - int(prev.get("injection_rate", 0))
    changes["water_prod_change"] = int(curr.get("WATER", 0)) - int(prev.get("WATER", 0))
    changes["water_source_change"] = int(curr.get("water_source_rate", 0)) - int(prev.get("water_source_rate", 0))
    return changes


def aggregate_production_trend(history_df):
    if history_df.empty:
        return pd.DataFrame(columns=["date", "bfpd", "OIL", "WATER", "water_cut_pct"])

    if {"bfpd", "OIL", "WATER", "water_cut_pct"}.issubset(history_df.columns):
        grouped = (
            history_df[["date", "bfpd", "OIL", "WATER"]]
            .groupby("date", as_index=False)
            .agg(bfpd=("bfpd", "sum"), OIL=("OIL", "sum"), WATER=("WATER", "sum"))
            .sort_values("date")
        )
        denominator = grouped["bfpd"].where(grouped["bfpd"].ne(0))
        grouped["water_cut_pct"] = (grouped["WATER"] / denominator * 100).round(1).fillna(0.0)
        return grouped
    return history_df


def aggregate_injection_trend(history_df):
    if history_df.empty:
        return pd.DataFrame(columns=["date", "status", "injection_rate"])

    if {"date", "injection_rate", "status"}.issubset(history_df.columns):
        inj_hist = history_df[history_df["status"].isin(["Injector", "Water Source"])]
        if inj_hist.empty:
            return pd.DataFrame(columns=["date", "status", "injection_rate"])
        return (
            inj_hist.groupby(["date", "status"])["injection_rate"]
            .sum()
            .reset_index()
            .sort_values("date")
        )
    return pd.DataFrame(columns=["date", "status", "injection_rate"])
