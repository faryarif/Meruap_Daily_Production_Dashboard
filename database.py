import numpy as np
import pandas as pd
import streamlit as st
from supabase import create_client

from constants import DATA_PROD_COLS, LOCATION_HEAD_COLS, NUMERIC_PROD_COLS


@st.cache_resource
def get_supabase():
    return create_client(
        st.secrets["supabase"]["url"].rstrip("/"),
        st.secrets["supabase"]["key"],
    )


def _rpc_df(function_name, params=None):
    response = get_supabase().rpc(function_name, params or {}).execute()
    return pd.DataFrame(response.data or [])


def _normalize_production(df):
    if df.empty:
        return pd.DataFrame(columns=DATA_PROD_COLS)

    df = df.rename(columns={
        "oil": "OIL",
        "gas": "GAS",
        "water": "WATER",
        "bfpd": "bfpd",
        "injection_rate": "injection_rate",
    })

    for col in NUMERIC_PROD_COLS:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")

    if "bfpd" not in df.columns:
        df["bfpd"] = df["OIL"] + df["WATER"]

    if "water_cut_pct" not in df.columns:
        bfpd = pd.to_numeric(df["bfpd"], errors="coerce").fillna(0)
        water = pd.to_numeric(df["WATER"], errors="coerce").fillna(0)
        df["water_cut_pct"] = np.where(
            bfpd > 0,
            (water / bfpd * 100).round(1),
            0.0,
        )

    return df


@st.cache_data(ttl=60, show_spinner=False)
def read_snapshot(date_str=None):
    params = {"p_date": date_str} if date_str else {}
    return _normalize_production(_rpc_df("dashboard_snapshot", params))


@st.cache_data(ttl=300, show_spinner=False)
def read_daily_trend(start_date=None, end_date=None):
    params = {}
    if start_date:
        params["p_start_date"] = start_date
    if end_date:
        params["p_end_date"] = end_date
    return _normalize_production(_rpc_df("dashboard_daily_trend", params))


@st.cache_data(ttl=60, show_spinner=False)
def read_well_history(alias, start_date=None, end_date=None):
    params = {"p_alias": alias}
    if start_date:
        params["p_start_date"] = start_date
    if end_date:
        params["p_end_date"] = end_date
    return _normalize_production(_rpc_df("dashboard_well_history", params))


@st.cache_data(ttl=300, show_spinner=False)
def read_locations():
    response = (
        get_supabase()
        .table("HeaderID")
        .select("ALIAS, field, status, latitude, longitude")
        .order("ALIAS")
        .execute()
    )
    if not response.data:
        return pd.DataFrame(columns=LOCATION_HEAD_COLS)

    df = pd.DataFrame(response.data)
    for col in ["latitude", "longitude"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df
