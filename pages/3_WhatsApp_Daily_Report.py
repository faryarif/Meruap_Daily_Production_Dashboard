"""WhatsApp daily operations report intake and review."""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import streamlit as st

from styles import inject_styles
from whatsapp_daily_report import parse_whatsapp_report, read_reports, save_report

st.set_page_config(page_title="WhatsApp Daily Report", page_icon="📋", layout="wide", initial_sidebar_state="collapsed")
inject_styles(st)

nav_daily, nav_monthly, nav_whatsapp = st.columns(3)
with nav_daily:
    if st.button("Daily Production Dashboard", key="report_nav_daily", use_container_width=True):
        st.switch_page("app.py")
with nav_monthly:
    if st.button("Monthly Reconciliation", key="report_nav_monthly", use_container_width=True):
        st.switch_page("pages/2_Monthly_Reconciliation.py")
with nav_whatsapp:
    if st.button("Laporan Harian WhatsApp", key="report_nav_whatsapp", use_container_width=True, type="primary"):
        st.switch_page("pages/3_WhatsApp_Daily_Report.py")

st.title("Laporan Harian WhatsApp")
st.caption("Salin pesan WhatsApp, periksa hasil pembacaan, lalu simpan sebagai laporan operasi harian.")

with st.expander("Input laporan WhatsApp", expanded=True):
    raw_message = st.text_area("Pesan WhatsApp", key="whatsapp_daily_raw", height=320,
                               placeholder="Tempel pesan laporan harian di sini…")
    if st.button("Baca pesan", type="primary", key="whatsapp_daily_parse"):
        if not raw_message.strip():
            st.warning("Tempel pesan laporan terlebih dahulu.")
        else:
            parsed = parse_whatsapp_report(raw_message)
            st.session_state["whatsapp_daily_payload"] = parsed
            parsed_date = parsed.get("report_date")
            st.session_state["whatsapp_daily_date"] = parsed_date.isoformat() if parsed_date else date.today().isoformat()
            st.success("Pesan dibaca. Tinjau dan koreksi tabel di bawah sebelum menyimpan.")

payload = st.session_state.get("whatsapp_daily_payload")
if payload:
    st.subheader("Tinjau hasil pembacaan")
    if payload.get("report_date"):
        st.caption(f"Tanggal yang terbaca dari judul pesan: {payload['report_date'].strftime('%d %B %Y')}")
    else:
        st.warning("Tanggal tidak terbaca otomatis. Pilih tanggal laporan yang benar di bawah.")

    report_date = st.date_input(
        "Tanggal laporan",
        value=date.fromisoformat(st.session_state.get("whatsapp_daily_date", date.today().isoformat())),
        key="whatsapp_daily_review_date",
    )

    def editable_table(label: str, key: str, rows: list[dict], help_text: str = "") -> pd.DataFrame:
        st.markdown(f"**{label}**")
        if help_text:
            st.caption(help_text)
        return st.data_editor(
            pd.DataFrame(rows), key=key, num_rows="dynamic", hide_index=True,
            use_container_width=True,
        )

    sot_df = editable_table("Aliran SOT dan lifting", "whatsapp_daily_sot", payload.get("sot_flows", []),
                            "Pastikan angka dan basis nett/gross sesuai pesan sumber.")
    loss_df = editable_table("Pasangan angka untuk analisis losses", "whatsapp_daily_losses",
                             payload.get("loss_pairs", []),
                             "Selisih = Dikirim − Diterima; nilai negatif menunjukkan gain/selisih penerimaan.")
    well_df = editable_table("Catatan sumur", "whatsapp_daily_wells", payload.get("well_notes", []),
                             "Catatan S/I LOP dan perubahan sumur diperiksa sebelum disimpan.")
    stock_df = editable_table("Stok tangki", "whatsapp_daily_stocks", payload.get("tank_stocks", []))
    quality_df = editable_table("Pembacaan BS&W tangki", "whatsapp_daily_quality", payload.get("tank_quality", []))
    road_df = editable_table("Transfer dan penerimaan road tank", "whatsapp_daily_road_tanks",
                             payload.get("road_tanks", []),
                             "Gross observed dan nett standard disimpan sebagai pengukuran berbeda.")

    if not loss_df.empty and {"Dikirim", "Diterima"}.issubset(loss_df.columns):
        preview = loss_df.copy()
        preview["Selisih (BO)"] = (pd.to_numeric(preview["Dikirim"], errors="coerce")
                                  - pd.to_numeric(preview["Diterima"], errors="coerce"))
        st.markdown("**Pratinjau selisih transfer**")
        st.dataframe(preview, hide_index=True, use_container_width=True)

    def records(frame: pd.DataFrame) -> list[dict]:
        return [] if frame is None or frame.empty else json.loads(frame.to_json(orient="records", date_format="iso"))

    if st.button("Simpan laporan terverifikasi", type="primary", key="whatsapp_daily_save"):
        if not raw_message.strip():
            st.error("Pesan sumber kosong; laporan tidak disimpan.")
        else:
            saved_payload = {
                "sot_flows": records(sot_df), "loss_pairs": records(loss_df),
                "well_notes": records(well_df), "tank_stocks": records(stock_df),
                "tank_quality": records(quality_df), "road_tanks": records(road_df),
            }
            try:
                save_report(report_date, raw_message, saved_payload)
                st.success(f"Laporan tanggal {report_date:%d %B %Y} tersimpan di Supabase.")
                for key in [
                    "whatsapp_daily_payload", "whatsapp_daily_date", "whatsapp_daily_review_date",
                    "whatsapp_daily_sot", "whatsapp_daily_losses", "whatsapp_daily_wells",
                    "whatsapp_daily_stocks", "whatsapp_daily_quality", "whatsapp_daily_road_tanks",
                    "whatsapp_daily_raw",
                ]:
                    st.session_state.pop(key, None)
                st.rerun()
            except Exception as exc:
                st.error(f"Laporan belum tersimpan. Periksa koneksi atau konfigurasi Supabase. Detail: {exc}")

st.divider()
st.subheader("Laporan tersimpan")
try:
    reports = read_reports()
except Exception as exc:
    reports = pd.DataFrame()
    st.error(f"Tidak dapat memuat laporan dari Supabase. Detail: {exc}")

if reports.empty:
    st.info("Belum ada laporan WhatsApp yang tersimpan.")
else:
    reports["report_date"] = pd.to_datetime(reports["report_date"], errors="coerce").dt.date
    reports["created_at"] = pd.to_datetime(reports["created_at"], errors="coerce")
    reports = reports.sort_values(["report_date", "created_at"], ascending=[False, False])
    report_ids = reports["id"].tolist()
    selected_id = st.selectbox(
        "Pilih tanggal / versi laporan", report_ids,
        format_func=lambda report_id: (
            f"{reports.loc[reports['id'].eq(report_id), 'report_date'].iloc[0]:%d %B %Y} · "
            f"{reports.loc[reports['id'].eq(report_id), 'created_at'].iloc[0]:%H:%M}"
        ),
        key="whatsapp_saved_report_id",
    )
    selected = reports.loc[reports["id"].eq(selected_id)].iloc[0]
    saved = selected["payload"] if isinstance(selected["payload"], dict) else {}

    tab_flow, tab_stock, tab_wells, tab_source = st.tabs(
        ["Alur SOT & losses", "Stok & road tank", "Catatan sumur", "Pesan sumber"]
    )
    with tab_flow:
        flows = pd.DataFrame(saved.get("sot_flows", []))
        if flows.empty:
            st.info("Tidak ada data aliran SOT pada laporan ini.")
        else:
            st.dataframe(flows, hide_index=True, use_container_width=True)
            if "Volume" in flows.columns:
                chart = flows.dropna(subset=["Volume"]).set_index("Tahap")[["Volume"]]
                if not chart.empty:
                    st.bar_chart(chart, use_container_width=True)
        pairs = pd.DataFrame(saved.get("loss_pairs", []))
        if not pairs.empty:
            pairs["Dikirim"] = pd.to_numeric(pairs.get("Dikirim"), errors="coerce")
            pairs["Diterima"] = pd.to_numeric(pairs.get("Diterima"), errors="coerce")
            pairs["Selisih (BO)"] = pairs["Dikirim"] - pairs["Diterima"]
            pairs["Selisih (%)"] = (
                pairs["Selisih (BO)"] / pairs["Dikirim"].where(pairs["Dikirim"].ne(0)) * 100
            ).round(1)
            pairs["Interpretasi"] = pairs["Selisih (BO)"].map(
                lambda v: "Loss" if pd.notna(v) and v > 0
                else "Gain / selisih penerimaan" if pd.notna(v) and v < 0
                else "Seimbang" if pd.notna(v) else "Belum lengkap"
            )
            st.markdown("**Analisis selisih transfer**")
            st.dataframe(pairs, hide_index=True, use_container_width=True)
    with tab_stock:
        stocks = pd.DataFrame(saved.get("tank_stocks", []))
        if stocks.empty:
            st.info("Tidak ada angka stok tangki pada laporan ini.")
        else:
            st.dataframe(stocks, hide_index=True, use_container_width=True)
        road = pd.DataFrame(saved.get("road_tanks", []))
        if road.empty:
            st.info("Tidak ada transfer road tank pada laporan ini.")
        else:
            st.markdown("**Transfer dan penerimaan road tank**")
            st.dataframe(road, hide_index=True, use_container_width=True)
        quality = pd.DataFrame(saved.get("tank_quality", []))
        if not quality.empty:
            st.markdown("**BS&W tangki**")
            st.dataframe(quality, hide_index=True, use_container_width=True)
    with tab_wells:
        wells = pd.DataFrame(saved.get("well_notes", []))
        if wells.empty:
            st.info("Tidak ada catatan sumur yang berhasil diekstrak.")
        else:
            st.dataframe(wells, hide_index=True, use_container_width=True)
    with tab_source:
        st.caption("Pesan asli disimpan sebagai jejak sumber laporan.")
        st.text_area("Pesan WhatsApp sumber", value=selected["source_message"], height=420, disabled=True)
