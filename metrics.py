import pandas as pd


def calculate_kpis(filtered_df):
    return {
        "total_bopd": int(filtered_df["OIL"].sum()),
        "active_count": int((filtered_df["status"] == "Oil").sum()),
        "shutin_count": int((filtered_df["status"] == "Shut-in").sum()),
        "down_count": int((filtered_df["status"] == "Down").sum()),
        "injector_count": int((filtered_df["status"] == "Injector").sum()),
        "water_source_count": int((filtered_df["status"] == "Water Source").sum()),
        "total_injection": int(
            filtered_df.loc[filtered_df["status"] == "Injector", "injection_rate"].sum()
        ),
        "total_water_source": int(
            filtered_df.loc[filtered_df["status"] == "Water Source", "WATER"].sum()
        ),
        "total_water_production": int(filtered_df["WATER"].sum()),
    }


def calculate_daily_changes(history_df):
    changes = {
        "bopd_change": None,
        "injection_change": None,
        "water_prod_change": None,
        "water_source_change": None,
    }
    if history_df.empty:
        return changes

    dates = sorted(history_df["date"].dropna().unique())
    if len(dates) < 2:
        return changes

    prev_date, curr_date = dates[-2], dates[-1]
    prev_df = history_df[history_df["date"] == prev_date]
    curr_df = history_df[history_df["date"] == curr_date]

    changes["bopd_change"] = int(curr_df["OIL"].sum()) - int(prev_df["OIL"].sum())
    changes["injection_change"] = int(
        curr_df.loc[curr_df["status"] == "Injector", "injection_rate"].sum()
    ) - int(prev_df.loc[prev_df["status"] == "Injector", "injection_rate"].sum())
    changes["water_prod_change"] = int(curr_df["WATER"].sum()) - int(prev_df["WATER"].sum())
    changes["water_source_change"] = int(
        curr_df.loc[curr_df["status"] == "Water Source", "WATER"].sum()
    ) - int(prev_df.loc[prev_df["status"] == "Water Source", "WATER"].sum())
    return changes


def aggregate_production_trend(history_df):
    if history_df.empty:
        return pd.DataFrame(columns=["date", "bfpd", "OIL", "WATER", "water_cut_pct"])

    trend_agg = (
        history_df.groupby("date")
        .agg(
            bfpd=("bfpd", "sum"),
            OIL=("OIL", "sum"),
            WATER=("WATER", "sum"),
            water_cut_pct=("water_cut_pct", "mean"),
        )
        .reset_index()
        .sort_values("date")
    )
    trend_agg["water_cut_pct"] = trend_agg["water_cut_pct"].round(1)
    return trend_agg


def aggregate_injection_trend(history_df):
    if history_df.empty:
        return pd.DataFrame(columns=["date", "status", "injection_rate"])

    inj_hist = history_df[history_df["status"].isin(["Injector", "Water Source"])]
    if inj_hist.empty:
        return pd.DataFrame(columns=["date", "status", "injection_rate"])

    return (
        inj_hist.groupby(["date", "status"])["injection_rate"]
        .sum()
        .reset_index()
        .sort_values("date")
    )
