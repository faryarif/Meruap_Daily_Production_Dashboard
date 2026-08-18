import io
from datetime import datetime

import pandas as pd
import streamlit as st
from supabase import create_client

REQUIRED_COLUMNS = ["date", "ALIAS", "OIL", "WATER", "injection_rate"]
COLUMN_ALIASES = {
    "date": ["date", "Date", "DATE", "production_date", "Production Date"],
    "ALIAS": ["ALIAS", "alias", "Alias", "well", "well_name", "Well Name", "WELL"],
    "OIL": ["OIL", "Oil", "oil", "BO", "BOPD", "bopd"],
    "WATER": ["WATER", "Water", "water", "BW", "BWPD", "bwpd"],
    "injection_rate": ["injection_rate", "Injection Rate", "injection rate", "INJECTION_RATE", "BF", "BFW", "Injection"],
}


def _service_key():
    try:
        return st.secrets["supabase"]["service_role_key"]
    except Exception:
        return None


@st.cache_resource
def get_supabase_admin():
    key = _service_key()
    if not key:
        return None
    return create_client(st.secrets["supabase"]["url"].rstrip("/"), key)


def _find_column(columns, candidates):
    normalized = {str(c).strip().lower(): c for c in columns}
    for candidate in candidates:
        if candidate.lower() in normalized:
            return normalized[candidate.lower()]
    return None


def read_excel(uploaded_file):
    raw = uploaded_file.getvalue()
    workbook = pd.ExcelFile(io.BytesIO(raw), engine="openpyxl")
    sheets = workbook.sheet_names
    frames = {sheet: pd.read_excel(io.BytesIO(raw), sheet_name=sheet, engine="openpyxl") for sheet in sheets}
    return frames


def normalize_production(df):
    if df.empty:
        return pd.DataFrame(columns=REQUIRED_COLUMNS), ["The selected sheet is empty."]

    rename = {}
    missing = []
    for target, candidates in COLUMN_ALIASES.items():
        source = _find_column(df.columns, candidates)
        if source is None:
            missing.append(target)
        else:
            rename[source] = target

    if missing:
        return pd.DataFrame(columns=REQUIRED_COLUMNS), [f"Missing required column(s): {', '.join(missing)}"]

    out = df.rename(columns=rename)[REQUIRED_COLUMNS].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    out["ALIAS"] = out["ALIAS"].astype("string").str.strip()

    for col in ["OIL", "WATER", "injection_rate"]:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    errors = []
    invalid_date = out["date"].isna()
    invalid_alias = out["ALIAS"].isna() | out["ALIAS"].eq("")
    negative_values = (out[["OIL", "WATER", "injection_rate"]] < 0).any(axis=1)

    if invalid_date.any():
        errors.append(f"{int(invalid_date.sum())} row(s) have an invalid date.")
    if invalid_alias.any():
        errors.append(f"{int(invalid_alias.sum())} row(s) have a blank ALIAS.")
    if negative_values.any():
        errors.append(f"{int(negative_values.sum())} row(s) have negative production/injection values.")

    duplicate_mask = out.duplicated(["date", "ALIAS"], keep=False)
    if duplicate_mask.any():
        errors.append(f"{int(duplicate_mask.sum())} row(s) belong to duplicate date + ALIAS keys in the Excel file.")

    out = out.dropna(subset=["date"])
    out = out[out["ALIAS"].notna() & out["ALIAS"].ne("")]
    out = out[~negative_values]
    out = out.drop_duplicates(["date", "ALIAS"], keep="last")
    out["date"] = out["date"].astype(str)
    return out, errors


def find_existing_keys(df):
    client = get_supabase_admin()
    if client is None or df.empty:
        return set()

    start_date = df["date"].min()
    end_date = df["date"].max()
    response = (
        client.table("ProdWellBasiss")
        .select("date, ALIAS")
        .gte("date", start_date)
        .lte("date", end_date)
        .execute()
    )
    return {(str(row["date"])[:10], str(row["ALIAS"]).strip()) for row in (response.data or [])}


def upsert_production(df, filename):
    client = get_supabase_admin()
    if client is None:
        raise RuntimeError("Missing [supabase].service_role_key in Streamlit secrets.")
    if df.empty:
        return {"inserted": 0, "updated": 0, "rows": 0}

    existing = find_existing_keys(df)
    records = df.to_dict(orient="records")
    for record in records:
        record["date"] = str(record["date"])

    inserted = sum((str(r["date"])[:10], str(r["ALIAS"]).strip()) not in existing for r in records)
    updated = len(records) - inserted

    batch_size = 1000
    for start in range(0, len(records), batch_size):
        client.table("ProdWellBasiss").upsert(records[start:start + batch_size], on_conflict="date,ALIAS").execute()

    client.table("production_upload_log").insert({
        "filename": filename,
        "uploaded_at": datetime.now().astimezone().isoformat(),
        "rows_read": len(records),
        "rows_inserted": inserted,
        "rows_updated": updated,
        "rows_rejected": 0,
        "status": "SUCCESS",
    }).execute()

    return {"inserted": inserted, "updated": updated, "rows": len(records)}
