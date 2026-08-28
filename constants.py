STATUS_COLORS = {
    "Oil": "#22c55e",
    "Water Source": "#1e3a8a",
    "Injector": "#3b82f6",
    "Gas": "#f97316",
    "Shut-in": "#eab308",
    "Down": "#6b7280",
    "Plug Abandon": "#ef4444",
    "Unknown": "#94a3b8",
}

DATA_PROD_COLS = ["date", "ALIAS", "OIL", "GAS", "WATER", "injection_rate", "reported_total"]
LOCATION_HEAD_COLS = ["ALIAS", "field", "status", "latitude", "longitude"]
NUMERIC_PROD_COLS = ["OIL", "GAS", "WATER", "injection_rate"]
COORDINATE_COLS = ["latitude", "longitude"]

FIELD_ORDER = ["North", "South", "East", "West"]

APP_TITLE = "Meruap Dashboard"
PAGE_ICON = "🛢️"
