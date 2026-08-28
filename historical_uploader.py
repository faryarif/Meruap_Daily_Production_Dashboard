import streamlit as st

from historical_etl import process_wds_files, to_excel_bytes, upload_wds_production


def render_wds_uploader():
    with st.expander("📚 Drag and Drop Excel WDS", expanded=False):
        st.caption("Drop multiple daily WDS reports here. The ETL extracts Date, Well, BO, BW, Gas, Total Injeksi bbls, and the daily Total Production from cell AH2, converts names such as M # 01 → M-01, and can upload the cleaned result to Supabase.")
        files = st.file_uploader(
            "Drop hundreds of WDS Excel reports here",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            key="wds_batch_uploader",
        )
        if not files:
            return

        st.info(f"{len(files):,} file(s) selected. Processing will happen when the files are loaded.")
        with st.spinner("Extracting WDS reports..."):
            result, errors = process_wds_files(files)

        injection_values = result["injection_rate"].fillna(0) if "injection_rate" in result.columns else None
        injection_total = float(injection_values.sum()) if injection_values is not None else 0.0
        active_injectors = int((injection_values > 0).sum()) if injection_values is not None else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Files processed", f"{len(files) - len(errors):,}")
        c2.metric("Rows extracted", f"{len(result):,}")
        c3.metric("Unique dates", f"{result['date'].nunique():,}" if not result.empty else "0")
        c4, c5 = st.columns(2)
        c4.metric("Active injector rows", f"{active_injectors:,}")
        c5.metric("Total Water Injection", f"{injection_total:,.0f} bbl")

        if not errors.empty:
            st.warning(f"{len(errors):,} file(s) could not be processed.")
            st.dataframe(errors, use_container_width=True, hide_index=True)

        if result.empty:
            st.error("No production rows were extracted.")
            return

        st.success(f"Extracted {len(result):,} unique date + well records.")
        preview = result.drop(columns=["source_file"]).copy()
        preview["_injection_sort"] = preview["injection_rate"].fillna(-1)
        preview = preview.sort_values(
            ["_injection_sort", "date", "ALIAS"],
            ascending=[False, True, True],
        ).drop(columns="_injection_sort")
        st.caption("Injector rows are shown first so the extracted injection values can be verified before upload.")
        st.dataframe(preview.head(200), use_container_width=True, hide_index=True)

        output = result.drop(columns=["source_file"])
        st.download_button(
            "⬇️ Download cleaned Excel",
            data=to_excel_bytes(output),
            file_name="WDS_production_extracted.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_wds_etl",
        )

        st.divider()
        confirm = st.checkbox("I reviewed the extracted data and want to update ProdWellBasiss.", key="confirm_wds_upload")
        if st.button("Upload extracted data to Supabase", type="primary", disabled=not confirm, key="upload_wds_button"):
            try:
                with st.spinner("Uploading extracted WDS production..."):
                    rows = upload_wds_production(output)
                st.cache_data.clear()
                st.success(f"Successfully uploaded {rows:,} date + well records, Total Injeksi bbls values, and the AH2 daily totals. Blank injection values did not overwrite existing injection_rate data.")
                st.rerun()
            except Exception as exc:
                st.error(f"WDS upload failed: {exc}")
