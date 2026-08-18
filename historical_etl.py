import io
import re
from datetime import datetime

import pandas as pd


def _find_date(raw_df):
    """Find a date anywhere in the first ~15 rows of the report header."""
    for r in range(min(15, len(raw_df))):
        for value in raw_df.iloc[r].tolist():
            if pd.isna(value):
                continue
            text = str(value).strip()
            match = re.search(r"(?:date\s*[:\-]?\s*)?(\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4})", text, re.I)
            if match:
                parsed = pd.to_datetime(match.group(1), dayfirst=True, errors="coerce")
                if not pd.isna(parsed):
                    return parsed.date()
            match = re.search(r"(?:date\s*[:\-]?\s*)?([A-Za-z]{3,9}\s+\d{1,2}[,\s]+\d{4})", text, re.I)
            if match:
                parsed = pd.to_datetime(match.group(1), errors="coerce")
                if not pd.isna(parsed):
                    return parsed.date()
    return None


def _normalise_well(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    # WDS convention: M # 01 -> M-01, while preserving suffixes such as M # 06 C.
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
    raw = pd.read_excel(io.BytesIO(uploaded_file.getvalue()), header=None, engine="openpyxl")
    report_date = _find_date(raw)
    header_row = _find_header_row(raw)
    if report_date is None:
        raise ValueError("Could not find the report date in the header.")
    if header_row is None:
        raise ValueError("Could not find Well / BO / BW columns.")

    table = pd.read_excel(io.BytesIO(uploaded_file.getvalue()), header=header_row, engine="openpyxl")
    columns = {str(c).strip().lower(): c for c in table.columns}

    def col(*names):
        for name in names:
            if name.lower() in columns:
                return columns[name.lower()]
        return None

    well_col = col("well")
    oil_col = col("bo", "oil")
    water_col = col("bw", "water")
    if not all([well_col, oil_col, water_col]):
        raise ValueError("Required columns Well, BO and BW were not found.")

    out = table[[well_col, oil_col, water_col]].copy()
    out.columns = ["ALIAS", "OIL", "WATER"]
    out["ALIAS"] = out["ALIAS"].map(_normalise_well)
    out["OIL"] = pd.to_numeric(out["OIL"], errors="coerce")
    out["WATER"] = pd.to_numeric(out["WATER"], errors="coerce")
    out = out[out["ALIAS"].notna() & out["ALIAS"].astype(str).str.strip().ne("")].copy()
    out["OIL"] = out["OIL"].fillna(0.0)
    out["WATER"] = out["WATER"].fillna(0.0)
    out["date"] = str(report_date)
    out = out[["date", "ALIAS", "OIL", "WATER"]]
    out = out.drop_duplicates(["date", "ALIAS"], keep="last")
    return out


def process_wds_files(uploaded_files):
    frames = []
    errors = []
    for file in uploaded_files:
        try:
            df = extract_wds_file(file)
            df["source_file"] = file.name
            frames.append(df)
        except Exception as exc:
            errors.append({"file": file.name, "error": str(exc)})

    if not frames:
        result = pd.DataFrame(columns=["date", "ALIAS", "OIL", "WATER", "source_file"])
    else:
        result = pd.concat(frames, ignore_index=True)
        result = result.sort_values(["date", "ALIAS"]).drop_duplicates(["date", "ALIAS"], keep="last").reset_index(drop=True)
    return result, pd.DataFrame(errors, columns=["file", "error"])


def to_excel_bytes(df):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Production")
    return buffer.getvalue()
