"""Shared ID gate for the Streamlit dashboard."""
import hmac

import streamlit as st

from meruap_brand import MERUAP_LOGO, MERUAP_LOGO_BASE64


def _render_brand():
    st.markdown(
        f"""
        <style>
        .meruap-brand-header {{
            display: flex; align-items: center; gap: 12px;
            padding: 2px 0 12px; margin-bottom: 10px;
            border-bottom: 1px solid #263144;
        }}
        .meruap-brand-header img {{
            display: block; width: 46px; height: 46px; object-fit: contain;
            padding: 2px; border-radius: 50%; background: #fff;
            box-sizing: border-box;
        }}
        .meruap-brand-name {{
            color: #fb923c; font-size: 1.2rem; line-height: 1.2;
            font-weight: 800; letter-spacing: .04em;
        }}
        .meruap-brand-subtitle {{
            color: #94a3b8; font-size: .68rem; letter-spacing: .12em;
            text-transform: uppercase;
        }}
        </style>
        <div class="meruap-brand-header">
          <img src="data:image/png;base64,{MERUAP_LOGO_BASE64}" alt="Meruap logo">
          <div>
            <div class="meruap-brand-name">MERUAP</div>
            <div class="meruap-brand-subtitle">Production Dashboard</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_app_header(active_page):
    """Render the brand and three page links in one top navigation row."""
    brand_col, daily_col, whatsapp_col, monthly_col = st.columns(
        [2.15, 1.7, 1.8, 1.8], vertical_alignment="center", gap="small"
    )
    with brand_col:
        logo_col, name_col = st.columns([1, 3.5], vertical_alignment="center", gap="small")
        with logo_col:
            st.image(MERUAP_LOGO, width=42)
        with name_col:
            st.markdown(
                '<div style="color:#fb923c;font-weight:800;letter-spacing:.04em;'
                'font-size:1.08rem;line-height:1.2">MERUAP</div>'
                '<div style="color:#94a3b8;font-size:.63rem;letter-spacing:.1em;'
                'text-transform:uppercase">Production Dashboard</div>',
                unsafe_allow_html=True,
            )

    nav_items = [
        (daily_col, "Laporan Produksi Harian", "daily", "app.py"),
        (whatsapp_col, "Laporan Lifting Harian", "whatsapp", "pages/3_WhatsApp_Daily_Report.py"),
        (monthly_col, "Laporan Lifting Bulanan", "monthly", "pages/2_Monthly_Reconciliation.py"),
    ]
    for column, label, page_key, target in nav_items:
        with column:
            if st.button(
                label,
                key=f"brand_nav_{active_page}_{page_key}",
                type="primary" if active_page == page_key else "secondary",
                use_container_width=True,
            ):
                st.switch_page(target)

    st.markdown(
        '<div style="height:1px;background:#263144;margin:7px 0 10px"></div>',
        unsafe_allow_html=True,
    )



def require_access():
    """Require the shared access ID before rendering any dashboard page."""
    access_config = st.secrets.get("access", {})
    expected_id = access_config.get("id") if hasattr(access_config, "get") else None

    if not isinstance(expected_id, str) or not expected_id:
        _render_brand()
        st.title("Akses Dashboard Meruap")
        st.error("ID akses belum dikonfigurasi untuk aplikasi ini.")
        st.markdown("Tambahkan ID di **Streamlit Settings → Secrets**:")
        st.code('[access]\nid = "GANTI_DENGAN_ID_AKSES_RAHASIA"')
        st.stop()

    if st.session_state.get("dashboard_access_granted") is True:
        with st.sidebar:
            st.caption("Akses dashboard aktif")
            if st.button("Keluar", key="dashboard_access_logout"):
                st.session_state.pop("dashboard_access_granted", None)
                st.rerun()
        return

    _render_brand()
    st.title("Akses Dashboard Meruap")
    st.caption("Masukkan ID akses yang diberikan pengelola dashboard.")
    with st.form("dashboard_access_login", clear_on_submit=True):
        entered_id = st.text_input("ID akses")
        submitted = st.form_submit_button("Masuk", type="primary")

    if submitted:
        if hmac.compare_digest(entered_id, expected_id):
            st.session_state["dashboard_access_granted"] = True
            st.rerun()
        else:
            st.error("ID akses tidak valid.")

    st.stop()
