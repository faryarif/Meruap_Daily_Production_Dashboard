import streamlit as st

from historical_etl import process_wds_files, to_excel_bytes, upload_wds_production


def render_wds_uploader():
    with st.expander("📚 Drag and Drop Excel WDS", expanded=False):
        st.caption("Drop multiple daily WDS reports here. The ETL extracts Date, Well, BO and BW, converts names such as M # 01 → M-01, and can upload the cleaned result to Supabase.")
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

        c1, c2, c3 = st.columns(3)
        c1.metric("Files processed", f"{len(files) - len(errors):,}")
        c2.metric("Rows extracted", f"{len(result):,}")
        c3.metric("Unique dates", f"{result['date'].nunique():,}" if not result.empty else "0")

        if not errors.empty:
            st.warning(f"{len(errors):,} file(s) could not be processed.")
            st.dataframe(errors, use_container_width=True, hide_index=True)

        if result.empty:
            st.error("No production rows were extracted.")
            return

        st.success(f"Extracted {len(result):,} unique date + well records.")
        st.dataframe(result.drop(columns=["source_file"]).head(200), use_container_width=True, hide_index=True)

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
                st.success(f"Successfully uploaded {rows:,} date + well records. Existing injection_rate values were not overwritten.")
                st.rerun()
            except Exception as exc:
                st.error(f"WDS upload failed: {exc}")
