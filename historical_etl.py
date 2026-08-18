import io
import re
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
from supabase import create_client


def _parse_report_date(value):
    """Parse WDS dates without letting pandas misinterpret 2-digit years.

    WDS reports may contain a true Excel datetime, an Excel serial date, or a
    text date such as 13-07-26 / 13-07-2026. Two-digit years are explicitly
    mapped to 2000-2069 rather than relying on pandas' date inference.
    """
    if pd.isna(value):
        return None

    if isinstance(value, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(value).date()

    # Excel serial date (1900 date system). Only accept plausible serials.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if 20000 <= number <= 80000:
            parsed = pd.Timestamp("1899-12-30") + pd.to_timedelta(number, unit="D")
            return parsed.date()

    text = str(value).strip()
    if not text:
        return None

    # Prefer an explicit numeric date embedded in text.
    match = re.search(r"(\d{1,2})\s*[-/]\s*(\d{1,2})\s*[-/]\s*(\d{2}|\d{4})", text)
    if match:
        day, month, year = map(int, match.groups())
        if year < 100:
            year += 2000 if year <= 69 else 1900
        try:
            return date(year, month, day)
        except ValueError:
            return None

    # Then handle textual dates such as 13 July 2026.
    match = re.search(r"([A-Za-z]{3,9})\s+(\d{1,2})[,\s]+(\d{4})", text)
    if match:
        try:
            return pd.to_datetime(match.group(0), format="%B %d %Y", errors="raise").date()
        except ValueError:
            try:
                return pd.to_datetime(match.group(0), errors="raise").date()
            except ValueError:
                return None

    return None


def _find_date(raw_df, filename=""):
    # First inspect the report header. WDS date is normally in the first rows.
    for r in range(min(15, len(raw_df))):
        for value in raw_df.iloc[r].tolist():
            parsed = _parse_report_date(value)
            if parsed is not None and 1990 <= parsed.year <= 2100:
                return parsed

    # Last-resort fallback: WDS filenames commonly contain DD-MM-YYYY.
    filename_match = re.search(r"(\d{1,2})[-_](\d{1,2})[-_](\d{4})", str(filename))
    if filename_match:
        day, month, year = map(int, filename_match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            pass

    return None


def _normalise_well(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    match = re.match(r"^\s*([A-Za-z]+)\s*#\s*(\d+)\s*([A-Za-z]*)\s*$", text)
    if match:
        return f"{match.group(1).upper()}-{int(match.group(2)):02d}{match.group(3).upper()}"
    return text


def _find_header_row(raw_df):
    for r in range(min(30, len(raw_df))):
        values = {str(v).strip().lower() for v in raw_df.iloc[r].tolist() if not pd.isna(v)}
        if "well" in values and ("bo" in values or "oil" in values) and ("bw" in values or "water" in values):
            return r
    return None


def extract_wds_file(uploaded_file):
    raw_bytes = uploaded_file.getvalue()
    raw = pd.read_excel(io.BytesIO(raw_bytes), header=None, engine="openpyxl")
    report_date = _find_date(raw, getattr(uploaded_file, "name", ""))
    header_row = _find_header_row(raw)
    if report_date is None:
        raise ValueError("Could not find a valid report date in the header or filename.")
    if header_row is None:
        raise ValueError("Could not find Well / BO / BW columns.")

    table = pd.read_excel(io.BytesIO(raw_bytes), header=header_row, engine="openpyxl")
    columns = {str(c).strip().lower(): c for c in table.columns}

    def col(*names):
        for name in names:
            if name.lower() in columns:
                return columns[name.lower()]
        return None

    well_col, oil_col, water_col = col("well"), col("bo", "oil"), col("bw", "water")
    if not all([well_col, oil_col, water_col]):
        raise ValueError("Required columns Well, BO and BW were not found.")

    out = table[[well_col, oil_col, water_col]].copy()
    out.columns = ["ALIAS", "OIL", "WATER"]
    out["ALIAS"] = out["ALIAS"].map(_normalise_well)
    out["OIL"] = pd.to_numeric(out["OIL"], errors="coerce").fillna(0.0)
    out["WATER"] = pd.to_numeric(out["WATER"], errors="coerce").fillna(0.0)
    out = out[out["ALIAS"].notna() & out["ALIAS"].astype(str).str.strip().ne("")].copy()
    out["date"] = report_date.isoformat()
    return out[["date", "ALIAS", "OIL", "WATER"]].drop_duplicates(["date", "ALIAS"], keep="last")


def process_wds_files(uploaded_files):
    frames, errors = [], []
    for file in uploaded_files:
        try:
            df = extract_wds_file(file)
            df["source_file"] = file.name
            frames.append(df)
        except Exception as exc:
            errors.append({"file": file.name, "error": str(exc)})

    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["date", "ALIAS", "OIL", "WATER", "source_file"])
    if not result.empty:
        result = result.sort_values(["date", "ALIAS"]).drop_duplicates(["date", "ALIAS"], keep="last").reset_index(drop=True)
    return result, pd.DataFrame(errors, columns=["file", "error"])


def to_excel_bytes(df):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Production")
    return buffer.getvalue()


def _admin_client():
    key = st.secrets["supabase"]["service_role_key"]
    return create_client(st.secrets["supabase"]["url"].rstrip("/"), key)


def upload_wds_production(df):
    """Upsert only date/ALIAS/OIL/WATER; do not overwrite an existing injection_rate."""
    if df.empty:
        return 0
    client = _admin_client()
    records = df[["date", "ALIAS", "OIL", "WATER"]].to_dict(orient="records")
    for start in range(0, len(records), 1000):
        client.table("ProdWellBasiss").upsert(
            records[start:start + 1000],
            on_conflict="date,ALIAS",
            default_to_null=False,
        ).execute()
    return len(records)
