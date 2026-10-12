"""WhatsApp daily operations report intake and review."""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from styles import inject_styles
from whatsapp_daily_report import parse_whatsapp_report, read_reports, save_report

st.set_page_config(page_title="WhatsApp Daily Report", page_icon="📋", layout="wide", initial_sidebar_state="collapsed")
inject_styles(st)

nav_daily, nav_whatsapp, nav_monthly = st.columns(3)
with nav_daily:
    if st.button("Laporan Produksi Harian", key="report_nav_daily", use_container_width=True):
        st.switch_page("app.py")
with nav_monthly:
    if st.button("Laporan Lifting Bulanan", key="report_nav_monthly", use_container_width=True):
        st.switch_page("pages/2_Monthly_Reconciliation.py")
with nav_whatsapp:
    if st.button("Laporan Lifting Harian", key="report_nav_whatsapp", use_container_width=True, type="primary"):
        st.switch_page("pages/3_WhatsApp_Daily_Report.py")

if st.session_state.pop("whatsapp_daily_reset_form", False):
    for key in [
        "whatsapp_daily_payload", "whatsapp_daily_source", "whatsapp_daily_date",
        "whatsapp_daily_review_date", "whatsapp_daily_sot", "whatsapp_daily_losses",
        "whatsapp_daily_wells", "whatsapp_daily_stocks", "whatsapp_daily_quality",
        "whatsapp_daily_road_tanks",
    ]:
        st.session_state.pop(key, None)
    st.session_state["whatsapp_daily_raw"] = ""

if st.session_state.get("whatsapp_daily_saved_message"):
    st.success(st.session_state.pop("whatsapp_daily_saved_message"))

with st.expander("Input laporan WhatsApp", expanded=False):
    draft_message = st.session_state.get("whatsapp_daily_raw", "")
    input_height = 160 if not draft_message.strip() else 280
    raw_message = st.text_area("Pesan WhatsApp", key="whatsapp_daily_raw", height=input_height,
                               placeholder="Tempel pesan laporan harian di sini…")
    if st.button("Baca pesan", type="primary", key="whatsapp_daily_parse"):
        if not raw_message.strip():
            st.warning("Tempel pesan laporan terlebih dahulu.")
        else:
            for key in [
                "whatsapp_daily_review_date", "whatsapp_daily_sot", "whatsapp_daily_losses",
                "whatsapp_daily_wells", "whatsapp_daily_stocks", "whatsapp_daily_quality",
                "whatsapp_daily_road_tanks",
            ]:
                st.session_state.pop(key, None)
            parsed = parse_whatsapp_report(raw_message)
            st.session_state["whatsapp_daily_payload"] = parsed
            parsed_date = parsed.get("report_date")
            st.session_state["whatsapp_daily_date"] = parsed_date.isoformat() if parsed_date else date.today().isoformat()
            st.session_state["whatsapp_daily_source"] = raw_message
            st.success("Pesan dibaca. Tinjau dan koreksi tabel di bawah sebelum menyimpan.")

payload = st.session_state.get("whatsapp_daily_payload")
if payload:
    st.subheader("Tinjau hasil pembacaan")
    if payload.get("report_date"):
        st.caption(f"Tanggal yang terbaca dari judul pesan: {payload['report_date'].strftime('%d %B %Y')}")
    else:
        st.warning("Tanggal tidak terbaca otomatis. Pilih tanggal laporan yang benar di bawah.")

    source_message = st.session_state.get("whatsapp_daily_source", raw_message)
    source_unchanged = raw_message == source_message
    if not source_unchanged:
        st.warning("Pesan berubah setelah dibaca. Tekan “Baca pesan” lagi agar hasil dan sumber tetap cocok.")

    report_date = st.date_input(
        "Tanggal laporan",
        value=date.fromisoformat(st.session_state.get("whatsapp_daily_date", date.today().isoformat())),
        key="whatsapp_daily_review_date",
    )

    def editable_table(label: str, key: str, rows: list[dict], help_text: str = "") -> pd.DataFrame:
        st.markdown(f"**{label}**")
        if help_text:
            st.caption(help_text)
        empty_columns = {
            "whatsapp_daily_sot": ["Tahap", "Volume", "Satuan", "Basis"],
            "whatsapp_daily_losses": ["Segmen", "Dikirim", "Diterima", "Satuan"],
            "whatsapp_daily_wells": ["Sumur", "Catatan", "Perubahan (BO)", "Durasi LOP (jam)"],
            "whatsapp_daily_stocks": ["Lokasi / tangki", "Stok (BO)", "BS&W (%)", "Basis"],
            "whatsapp_daily_quality": ["Tangki", "BS&W (%)"],
            "whatsapp_daily_road_tanks": ["Arah / metode", "Volume (BO)", "Unit truk", "Basis"],
        }
        frame = pd.DataFrame(rows) if rows else pd.DataFrame(columns=empty_columns.get(key, []))
        return st.data_editor(
            frame, key=key, num_rows="dynamic", hide_index=True,
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

    if st.button("Simpan laporan terverifikasi", type="primary", key="whatsapp_daily_save", disabled=not source_unchanged):
        if not raw_message.strip():
            st.error("Pesan sumber kosong; laporan tidak disimpan.")
        else:
            saved_payload = {
                "sot_flows": records(sot_df), "loss_pairs": records(loss_df),
                "well_notes": records(well_df), "tank_stocks": records(stock_df),
                "tank_quality": records(quality_df), "road_tanks": records(road_df),
            }
            try:
                save_report(report_date, source_message, saved_payload)
                st.session_state["whatsapp_daily_saved_message"] = (
                    f"Laporan tanggal {report_date:%d %B %Y} tersimpan di Supabase."
                )
                st.session_state["whatsapp_daily_reset_form"] = True
                st.rerun()
            except Exception as exc:
                st.error(f"Laporan belum tersimpan. Periksa koneksi atau konfigurasi Supabase. Detail: {exc}")

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

    monthly_reports = (
        reports.dropna(subset=["report_date"])
        .sort_values(["report_date", "created_at"], ascending=[True, True])
        .drop_duplicates(subset=["report_date"], keep="last")
        .copy()
    )
    monthly_reports["month_key"] = pd.to_datetime(monthly_reports["report_date"]).dt.strftime("%Y-%m")
    month_options = sorted(monthly_reports["month_key"].dropna().unique().tolist(), reverse=True)
    month_names = [
        "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember",
    ]
    month_key = st.selectbox(
        "Bulan laporan",
        month_options,
        format_func=lambda value: f"{month_names[int(value[5:7]) - 1]} {value[:4]}",
        key="whatsapp_month_chart_period",
    )
    month_rows = monthly_reports[monthly_reports["month_key"].eq(month_key)].copy()
    st.metric("Hari dengan laporan", f"{len(month_rows):,}")

    flow_rows, loss_rows, stock_rows, road_rows = [], [], [], []
    for _, report in month_rows.iterrows():
        report_day = pd.Timestamp(report["report_date"])
        payload_data = report["payload"] if isinstance(report["payload"], dict) else {}

        for item in payload_data.get("sot_flows", []):
            value = pd.to_numeric(item.get("Volume"), errors="coerce")
            if pd.notna(value):
                flow_rows.append({
                    "Tanggal": report_day,
                    "Tahap": item.get("Tahap", "Tahap tidak diketahui"),
                    "Volume (BO)": float(value),
                })

        for item in payload_data.get("loss_pairs", []):
            sent = pd.to_numeric(item.get("Dikirim"), errors="coerce")
            received = pd.to_numeric(item.get("Diterima"), errors="coerce")
            if pd.notna(sent) and pd.notna(received):
                loss_rows.append({
                    "Tanggal": report_day,
                    "Segmen": item.get("Segmen", "Segmen tidak diketahui"),
                    "Selisih (BO)": float(sent - received),
                })

        for item in payload_data.get("tank_stocks", []):
            value = pd.to_numeric(item.get("Stok (BO)"), errors="coerce")
            if pd.notna(value):
                stock_rows.append({
                    "Tanggal": report_day,
                    "Lokasi / tangki": item.get("Lokasi / tangki", "Lokasi tidak diketahui"),
                    "Stok (BO)": float(value),
                })

        for item in payload_data.get("road_tanks", []):
            value = pd.to_numeric(item.get("Volume (BO)"), errors="coerce")
            if pd.notna(value):
                road_rows.append({
                    "Tanggal": report_day,
                    "Arah / metode": item.get("Arah / metode", "Metode tidak diketahui"),
                    "Volume (BO)": float(value),
                })

    flow_tab_month, loss_tab_month, stock_tab_month, road_tab_month = st.tabs(
        ["Aliran SOT & lifting", "Loss / gain", "Stok tangki", "Road tank"]
    )

    def style_month_figure(fig):
        fig.update_layout(
            height=360,
            margin=dict(l=10, r=10, t=20, b=10),
            paper_bgcolor="#0b1220",
            plot_bgcolor="#0b1220",
            font=dict(color="#e2e8f0"),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        )
        fig.update_xaxes(title=None, gridcolor="#263144", tickformat="%d %b")
        fig.update_yaxes(gridcolor="#263144")
        return fig

    with flow_tab_month:
        flows_month = pd.DataFrame(flow_rows)
        if flows_month.empty:
            st.info("Belum ada angka aliran SOT/lifting untuk bulan ini.")
        else:
            stages = sorted(flows_month["Tahap"].dropna().unique().tolist())
            preferred_stages = [
                "OPS Terima STA-SRL",
                "Terima di SPU BJB",
                "Terima di PPP Allocation",
                "Lifting quantity KM-3 Sei Gerong",
            ]
            selected_stages = st.multiselect(
                "Tahap yang ditampilkan",
                stages,
                default=[stage for stage in preferred_stages if stage in stages],
                key="whatsapp_month_flow_stages",
            )
            selected_flows = flows_month[flows_month["Tahap"].isin(selected_stages)]
            if selected_flows.empty:
                st.info("Pilih satu atau beberapa tahap untuk melihat tren.")
            else:
                fig = go.Figure()
                for stage, series in selected_flows.groupby("Tahap"):
                    series = series.sort_values("Tanggal")
                    fig.add_trace(go.Scatter(
                        x=series["Tanggal"],
                        y=series["Volume (BO)"],
                        name=stage,
                        mode="lines+markers",
                        connectgaps=False,
                        hovertemplate="%{x|%d %b}<br>%{y:,.1f} BO<extra>%{fullData.name}</extra>",
                    ))
                fig.update_yaxes(title="Volume (BO)")
                st.plotly_chart(style_month_figure(fig), use_container_width=True, config={"displayModeBar": False})

    with loss_tab_month:
        losses_month = pd.DataFrame(loss_rows)
        if losses_month.empty:
            st.info("Belum ada pasangan angka kirim-terima yang lengkap untuk bulan ini.")
        else:
            fig = go.Figure()
            for segment, series in losses_month.groupby("Segmen"):
                series = series.sort_values("Tanggal")
                fig.add_trace(go.Scatter(
                    x=series["Tanggal"],
                    y=series["Selisih (BO)"],
                    name=segment,
                    mode="lines+markers",
                    connectgaps=False,
                    hovertemplate="%{x|%d %b}<br>%{y:+,.1f} BO<extra>%{fullData.name}</extra>",
                ))
            fig.add_hline(y=0, line_dash="dash", line_color="#94a3b8")
            fig.update_yaxes(title="Loss (+) / gain (−), BO")
            st.plotly_chart(style_month_figure(fig), use_container_width=True, config={"displayModeBar": False})

    with stock_tab_month:
        stocks_month = pd.DataFrame(stock_rows)
        if stocks_month.empty:
            st.info("Belum ada data stok tangki untuk bulan ini.")
        else:
            fig = go.Figure()
            for location, series in stocks_month.groupby("Lokasi / tangki"):
                series = series.sort_values("Tanggal")
                fig.add_trace(go.Scatter(
                    x=series["Tanggal"],
                    y=series["Stok (BO)"],
                    name=location,
                    mode="lines+markers",
                    connectgaps=False,
                    hovertemplate="%{x|%d %b}<br>%{y:,.1f} BO<extra>%{fullData.name}</extra>",
                ))
            fig.update_yaxes(title="Stok (BO)")
            st.plotly_chart(style_month_figure(fig), use_container_width=True, config={"displayModeBar": False})

    with road_tab_month:
        road_month = pd.DataFrame(road_rows)
        if road_month.empty:
            st.info("Belum ada data transfer/penerimaan road tank untuk bulan ini.")
        else:
            fig = go.Figure()
            for method, series in road_month.groupby("Arah / metode"):
                series = series.sort_values("Tanggal")
                fig.add_trace(go.Scatter(
                    x=series["Tanggal"],
                    y=series["Volume (BO)"],
                    name=method,
                    mode="lines+markers",
                    connectgaps=False,
                    hovertemplate="%{x|%d %b}<br>%{y:,.1f} BO<extra>%{fullData.name}</extra>",
                ))
            fig.update_yaxes(title="Volume road tank (BO)")
            st.plotly_chart(style_month_figure(fig), use_container_width=True, config={"displayModeBar": False})

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
