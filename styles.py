APP_CSS = """
<style>
.stApp { background-color: #0b1220; color: #e2e8f0; }
[data-testid="stMetric"] { background-color: #18243a; border: 1px solid #3b4f6d; border-radius: 10px; padding: 14px 16px; box-shadow: 0 10px 26px rgba(0, 0, 0, 0.58), 0 3px 8px rgba(56, 189, 248, 0.12); }
[data-testid="stMetricLabel"] { color: #64748b; }
[data-testid="stMetricValue"], [data-testid="stMetricValue"] > div { font-size: 1.45rem !important; line-height: 1.15; }
section[data-testid="stSidebar"] { background-color: #0f1729; }
h1, h2, h3 { color: #e2e8f0 !important; }
.block-container { padding-top: 4.5rem; }
[data-testid="stToolbar"] { display: none; }
[data-testid="stDecoration"] { display: none; }
/* Keep sidebar controls available without a fixed opaque overlay. */
header[data-testid="stHeader"] {
    background: transparent !important;
    box-shadow: none !important;
    pointer-events: none;
}
header[data-testid="stHeader"] button,
header[data-testid="stHeader"] a,
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"] {
    pointer-events: auto;
}
[data-testid="collapsedControl"] { display: unset; }
</style>
"""


def inject_styles(st):
    st.markdown(APP_CSS, unsafe_allow_html=True)
