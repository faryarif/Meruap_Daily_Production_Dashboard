# Meruap Daily Production Dashboard

A Streamlit dashboard for daily oil, gas, water, and injection production monitoring, well performance review, and monthly production-to-lifting reconciliation. The dashboard reads production through Supabase RPCs so it does not download the full production table into the app.

## Dashboard pages

- **Daily Production Dashboard** (`app.py`): production KPIs and daily changes, field and well status, well map, production and injection trends, well decline review, and statistical water-cut alerts. Supports batch upload of WDS Excel reports.
- **Monthly Production & Lifting** (`pages/2_Monthly_Reconciliation.py`): monthly field-to-lifting reconciliation, production flow, tank transfers, trends, and loss/gain analysis. Accepts monthly `.xls` and `.xlsx` workbooks.
- **WhatsApp Daily Lifting Report** (`pages/3_WhatsApp_Daily_Report.py`): paste a daily operations message, review and edit extracted SOT/lifting flows, transfer differences, well notes, tank stocks, and road-tank movements, then save the verified report.

## Technology

- Python, Streamlit, pandas, Plotly, NumPy
- Supabase (PostgreSQL and RPC)
- Excel parsing with openpyxl and xlrd

## Run locally

Use Python 3.10 or newer, then install the project dependencies:

```bash
python -m venv .venv
# Windows:
.venv\\Scripts\\activate
# macOS/Linux:
source .venv/bin/activate

python -m pip install -r requirements.txt
```

Create `.streamlit/secrets.toml` with your Supabase project URL and keys:

```toml
[supabase]
url = "https://YOUR_PROJECT_REF.supabase.co"
key = "YOUR_DASHBOARD_ACCESS_KEY"
service_role_key = "YOUR_SERVER_SIDE_SERVICE_ROLE_KEY"
```

The dashboard uses `supabase.url` and `supabase.key` for its read client. Upload and report-saving operations use `supabase.service_role_key` server-side. Keep all keys private: do not commit `secrets.toml`, put a service-role key in client-side code, or share it in screenshots or logs.

Start the app:

```bash
streamlit run app.py
```

## Supabase setup

1. Configure the production tables and core dashboard RPCs used by the app: `dashboard_snapshot`, `dashboard_all_layer_snapshot`, `dashboard_daily_trend`, and `dashboard_well_history`. Their SQL must be compatible with the current columns consumed by `database.py`. These core production RPC definitions are managed separately from the two scripts below.
2. Run [`sql/monthly_lifting_reconciliation.sql`](sql/monthly_lifting_reconciliation.sql) to create the monthly reconciliation table and RPC.
3. Run [`sql/whatsapp_daily_reports.sql`](sql/whatsapp_daily_reports.sql) to create the WhatsApp daily reports table.
4. Confirm the `HeaderID` table contains well aliases, fields, statuses, and coordinates required by the dashboard.

Use a Supabase service-role key only in Streamlit's server-side secrets. The monthly and WhatsApp SQL scripts restrict access to the service role; review row-level security and policies before deployment.

## Data flow and performance

The daily dashboard requests snapshots, trends, and per-well history through bounded RPCs rather than loading the 400k+ row production table into Streamlit. The decline-review feature reads a bounded date window and filters to `UNIQUEID` values ending in `:AllLayer` so completion-layer rows such as tubing and casing are not counted as separate wells.

## Tests

Run the repository's unit tests with:

```bash
python -m unittest discover -v
```

## Main modules

- `database.py` — Supabase RPC and table reads
- `historical_etl.py`, `historical_uploader.py` — WDS Excel extraction and upload
- `monthly_reconciliation.py` — monthly workbook parsing, reconciliation, and charts
- `whatsapp_daily_report.py` — WhatsApp message parsing and report persistence
- `charts.py`, `maps.py`, `metrics.py` — dashboard visualizations and KPI calculations
- `water_cut_alerts.py`, `decline_review.py` — well alerts and production decline review
