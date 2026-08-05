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


@st.cache_data(ttl=30, show_spinner=False)
def read_data():
    client = get_supabase()
    resp = (
        client.table("ProdWellBasiss")
        .select("date, ALIAS, OIL, WATER, injection_rate")
        .order("date")
        .execute()
    )
    if not resp.data:
        return None, pd.DataFrame(columns=DATA_PROD_COLS)

    df = pd.DataFrame(resp.data)
    for col in NUMERIC_PROD_COLS:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    latest_date = df["date"].max()
    current_df = df[df["date"] == latest_date].drop(columns=["date"]).reset_index(drop=True)
    return current_df, df


@st.cache_data(ttl=30, show_spinner=False)
def read_locations():
    client = get_supabase()
    resp = (
        client.table("HeaderID")
        .select("ALIAS, field, status, latitude, longitude")
        .execute()
    )
    if not resp.data:
        return pd.DataFrame(columns=LOCATION_HEAD_COLS)

    df = pd.DataFrame(resp.data)
    for col in ["latitude", "longitude"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df
