"""Paste, review, persist, and display WhatsApp daily operations reports."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st
from supabase import create_client

MONTHS_ID = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "agustus": 8,
    "september": 9, "oktober": 10, "november": 11, "desember": 12,
}

SOT_LABELS = [
    ("OPS Terima STA-SRL", "OPS Terima STA-SRL"),
    ("Kirim STA SRL To SPU BJB", "Kirim STA SRL ke SPU BJB"),
    ("Terima di SPU BJB", "Terima di SPU BJB"),
    ("Pumping SPU to PPP", "Pumping SPU ke PPP"),
    ("Total Pumping SPU to PPP", "Total pumping SPU ke PPP"),
    ("Terima di PPP Allocation", "Terima di PPP Allocation"),
    ("Pumping to SPPP Allocation", "Pumping ke SPPP Allocation"),
    ("Supply to KM-03 Sei Gerong", "Supply ke KM-03 Sei Gerong"),
    ("Lifting Qtty Km3 Sei Gerong", "Lifting quantity KM-3 Sei Gerong"),
]

LOSS_PAIRS = [
    ("Pumping SPU → PPP", "Pumping SPU to PPP", "Terima di PPP Allocation"),
    ("Supply KM-03 → Lifting KM-3", "Supply to KM-03 Sei Gerong", "Lifting Qtty Km3 Sei Gerong"),
]

STOCK_LABELS = [
    ("Block Station A", "Block Station A"),
    ("Block Station B", "Block Station B"),
    ("Staging Area SRL", "Staging Area SRL"),
    ("Stock SPU BJB", "Stock SPU BJB"),
    ("Stock PPP Tempino", "Stock PPP Tempino"),
]


def parse_indonesian_number(value: str | None) -> float | None:
    """Read Indonesian thousands/decimal separators without silently guessing malformed text."""
    if value is None:
        return None
    text = str(value).strip().replace(" ", "")
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    if text.startswith("-"):
        negative = True
        text = text[1:]
    if "," in text and "." in text:
        decimal_sep = "," if text.rfind(",") > text.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        text = text.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif "," in text:
        tail = text.rsplit(",", 1)[-1]
        text = text.replace(",", "." if len(tail) != 3 else "")
    elif "." in text:
        tail = text.rsplit(".", 1)[-1]
        if len(tail) == 3 and text.count(".") == 1:
            text = text.replace(".", "")
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return -number if negative else number


def _label_pattern(label: str) -> str:
    return r"\s+".join(re.escape(part) for part in label.split())


def _line_value(message: str, label: str, occurrence: int = 0) -> float | None:
    pattern = re.compile(
        rf"^\s*{_label_pattern(label)}\s*=\s*(\(?\s*-?\s*\d[\d.,]*\s*\)?)",
        re.IGNORECASE | re.MULTILINE,
    )
    matches = pattern.findall(message)
    if occurrence >= len(matches):
        return None
    return parse_indonesian_number(matches[occurrence])


def _report_date(message: str) -> date | None:
    match = re.search(
        r"\b(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})\b",
        message,
        re.IGNORECASE,
    )
    if not match:
        return None
    month = MONTHS_ID.get(match.group(2).lower())
    if not month:
        return None
    try:
        return date(int(match.group(3)), month, int(match.group(1)))
    except ValueError:
        return None


def parse_whatsapp_report(message: str) -> dict[str, Any]:
    """Extract the report fields currently requested; every result remains editable."""
    sot_rows = []
    for label, display in SOT_LABELS:
        sot_rows.append({
            "Tahap": display,
            "Volume": _line_value(message, label),
            "Satuan": "BO",
            "Basis": "nett std",
        })

    loss_rows = []
    for display, sent_label, received_label in LOSS_PAIRS:
        loss_rows.append({
            "Segmen": display,
            "Dikirim": _line_value(message, sent_label),
            "Diterima": _line_value(message, received_label),
            "Satuan": "BO",
        })

    stock_rows = []
    for label, display in STOCK_LABELS:
        found = re.findall(
            rf"^\s*{_label_pattern(label)}\s*=\s*(\(?\s*-?\s*[\d.,]+)\s*bo\b([^\r\n]*)",
            message,
            re.IGNORECASE | re.MULTILINE,
        )
        for index, (raw_volume, tail) in enumerate(found):
            basis_match = re.search(r"nett\s+(obsv|std)", tail, re.IGNORECASE)
            bsw_match = re.search(r"([\d.,]+)\s*%", tail)
            basis = basis_match.group(0).lower() if basis_match else ""
            name = display
            if label == "Staging Area SRL":
                name = f"{display} ({basis or f'entry {index + 1}'})"
            stock_rows.append({
                "Lokasi / tangki": name,
                "Stok (BO)": parse_indonesian_number(raw_volume),
                "BS&W (%)": parse_indonesian_number(bsw_match.group(1)) if bsw_match else None,
                "Basis": basis,
            })

    quality_rows = []
    for line in message.splitlines():
        match = re.match(r"^\s*Bs&W\s+(T\d+)\s*=\s*([\d.,]+)\s*%", line, re.IGNORECASE)
        if match:
            quality_rows.append({
                "Tangki": match.group(1).upper(),
                "BS&W (%)": parse_indonesian_number(match.group(2)),
            })

    road_rows = []
    for label, display in [
        ("BJB", "Transfer ke BJB — gross observed"),
        ("Road tank", "Transfer ke BJB — nett standard"),
        ("BJB", "Penerimaan di BJB — gross observed"),
        ("Road tank", "Penerimaan — nett standard"),
    ]:
        section = "Transferred to" if len(road_rows) < 2 else "Received at"
        section_match = re.search(
            rf"_{re.escape(section)}_\s*=(.*?)(?=^\s*_[^_\r\n]+_\s*=|^\s*_[^_\r\n]+_\s*$|\Z)",
            message,
            re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
        section_text = section_match.group(1) if section_match else ""
        value = _line_value(section_text, label)
        if value is None:
            road_rows.append({
                "Arah / metode": display,
                "Volume (BO)": None,
                "Unit truk": None,
                "Basis": "gross obs" if "gross" in display else "nett std",
            })
        else:
            units_match = re.search(r"/\s*(\d+)\s*Unit", section_text, re.IGNORECASE)
            road_rows.append({
                "Arah / metode": display,
                "Volume (BO)": value,
                "Unit truk": int(units_match.group(1)) if units_match and "gross" in display else None,
                "Basis": "gross obs" if "gross" in display else "nett std",
            })

    well_rows = []
    low_match = re.search(
        r"^\s*M[#-]\s*22\s*=\s*(\(?\s*-?\s*[\d.,]+)[^\r\n]*?(S/I\s+LOP\s+\d+\s*Jam)?",
        message,
        re.IGNORECASE | re.MULTILINE,
    )
    if low_match:
        hours = re.search(r"(\d+)\s*Jam", low_match.group(0), re.IGNORECASE)
        well_rows.append({
            "Sumur": "M-22",
            "Catatan": "S/I LOP" if "S/I" in low_match.group(0).upper() else "Low vs kemarin",
            "Perubahan (BO)": parse_indonesian_number(low_match.group(1)),
            "Durasi LOP (jam)": int(hours.group(1)) if hours else None,
        })

    road_rows = [
        {"Arah / metode": "Transfer ke BJB — gross observed", "Volume (BO)": _line_value(_road_section(message, "Transferred to"), "BJB"), "Unit truk": _truck_count(_road_section(message, "Transferred to"), "BJB"), "Basis": "gross obs"},
        {"Arah / metode": "Transfer ke BJB — nett standard", "Volume (BO)": _line_value(_road_section(message, "Transferred to"), "Road tank"), "Unit truk": None, "Basis": "nett std"},
        {"Arah / metode": "Penerimaan di BJB — gross observed", "Volume (BO)": _line_value(_road_section(message, "Received at"), "BJB"), "Unit truk": _truck_count(_road_section(message, "Received at"), "BJB"), "Basis": "gross obs"},
        {"Arah / metode": "Penerimaan — nett standard", "Volume (BO)": _line_value(_road_section(message, "Received at"), "Road tank"), "Unit truk": None, "Basis": "nett std"},
    ]
    return {
        "report_date": _report_date(message),
        "sot_flows": sot_rows,
        "loss_pairs": loss_rows,
        "well_notes": well_rows,
        "tank_stocks": stock_rows,
        "tank_quality": quality_rows,
        "road_tanks": road_rows,
    }


def _road_section(message: str, section: str) -> str:
    match = re.search(
        rf"_{re.escape(section)}_\s*=(.*?)(?=^\s*_[^_\r\n]+_\s*=|^\s*_[^_\r\n]+_\s*$|\Z)",
        message,
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else ""


def _truck_count(section: str, label: str) -> int | None:
    match = re.search(
        rf"^\s*{_label_pattern(label)}\s*=.*?/\s*(\d+)\s*Unit",
        section,
        re.IGNORECASE | re.MULTILINE,
    )
    return int(match.group(1)) if match else None


def _client():
    return create_client(
        st.secrets["supabase"]["url"].rstrip("/"),
        st.secrets["supabase"]["service_role_key"],
    )


def save_report(report_date: date, source_message: str, payload: dict[str, Any]) -> None:
    record = {
        "report_date": report_date.isoformat(),
        "source_message": source_message,
        "payload": payload,
    }
    response = _client().table("whatsapp_daily_reports").insert(record).execute()
    if response.data is None:
        raise RuntimeError("Supabase did not confirm saving the daily report.")


def read_reports(limit: int = 100) -> pd.DataFrame:
    response = (
        _client()
        .table("whatsapp_daily_reports")
        .select("id,report_date,source_message,payload,created_at")
        .order("report_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return pd.DataFrame(response.data or [])
