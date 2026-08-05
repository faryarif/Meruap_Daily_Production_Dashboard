import numpy as np
import pandas as pd

from constants import COORDINATE_COLS, DATA_PROD_COLS, FIELD_ORDER, LOCATION_HEAD_COLS, NUMERIC_PROD_COLS


def ensure_production_columns(df):
    df = df.copy()
    for col in DATA_PROD_COLS:
        if col not in df.columns:
            df[col] = 0 if col in NUMERIC_PROD_COLS else None
    for col in NUMERIC_PROD_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return df


def ensure_location_columns(df):
    df = df.copy()
    for col in LOCATION_HEAD_COLS:
        if col not in df.columns:
            df[col] = np.nan
    for col in COORDINATE_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def add_bfpd(df):
    df = df.copy()
    df["bfpd"] = df["OIL"] + df["WATER"]
    return df


def add_water_cut(df):
    df = df.copy()
    if "bfpd" not in df.columns:
        df = add_bfpd(df)
    df["water_cut_pct"] = (
        df["WATER"] / df["bfpd"].replace(0, np.nan) * 100
    ).round(1).fillna(0)
    return df


def add_derived_metrics(df):
    return add_water_cut(add_bfpd(df))


def enrich_with_locations(production_df, locations_df, include_all_location_columns=True):
    production_df = add_derived_metrics(ensure_production_columns(production_df))
    locations_df = ensure_location_columns(locations_df)
    location_cols = LOCATION_HEAD_COLS if include_all_location_columns else ["ALIAS", "status"]
    enriched = production_df.merge(locations_df[location_cols], on="ALIAS", how="left")
    if "status" in enriched.columns:
        enriched["status"] = enriched["status"].fillna("Unknown")
    return enriched


def prepare_dashboard_frames(current_df, history_df, locations_df):
    locations_df = ensure_location_columns(locations_df)
    history_df = ensure_production_columns(history_df)

    history_enriched = enrich_with_locations(
        history_df,
        locations_df,
        include_all_location_columns=False,
    )

    if current_df is None or current_df.empty:
        current_enriched = current_df
    else:
        current_enriched = enrich_with_locations(current_df, locations_df)

    return current_enriched, history_enriched, locations_df


def available_dates(history_df):
    if history_df.empty or "date" not in history_df.columns:
        return []
    return sorted(history_df["date"].dropna().unique(), reverse=True)


def snapshot_for_date(history_df, locations_df, selected_date_str, fallback_df):
    if (
        not selected_date_str
        or history_df.empty
        or selected_date_str not in history_df["date"].values
    ):
        return fallback_df

    snapshot = (
        history_df[history_df["date"] == selected_date_str]
        .drop(columns=["date", "status"], errors="ignore")
        .reset_index(drop=True)
    )
    return enrich_with_locations(snapshot, locations_df)


def filter_by_field(df, field_filter):
    if field_filter == "All":
        return df
    return df[df["field"] == field_filter]


def field_options(df):
    if df is None or df.empty or "field" not in df.columns:
        return ["All"]
    return ["All"] + sorted(df["field"].dropna().unique().tolist())


def missing_coordinate_aliases(df):
    if df is None or df.empty:
        return []
    missing = df["latitude"].isna() | df["longitude"].isna()
    return df.loc[missing, "ALIAS"].dropna().astype(str).tolist()


def order_field_totals(field_totals):
    field_totals = field_totals.copy()
    field_totals["sort_key"] = field_totals["field"].fillna("").apply(
        lambda field: next(
            (i for i, key in enumerate(FIELD_ORDER) if key.lower() in field.lower()),
            len(FIELD_ORDER),
        )
    )
    return field_totals.sort_values("sort_key").drop(columns="sort_key")
