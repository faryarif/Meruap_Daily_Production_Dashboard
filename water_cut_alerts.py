"""Water-cut alerts from valid, daily AllLayer measurements."""
from collections import defaultdict
from datetime import date, timedelta
from math import isfinite
from statistics import mean, stdev

BASELINE_DAYS = 30
MIN_VALID_DAYS = 20
SIGMA_FLOOR_PP = 0.1


def assess_water_cut(records, selected_date, aliases):
    end = date.fromisoformat(str(selected_date)[:10])
    start = end - timedelta(days=BASELINE_DAYS)
    allowed = set(aliases)
    daily = defaultdict(list)
    for row in records:
        alias = row.get("ALIAS")
        if alias not in allowed or row.get("UNIQUEID") != f"{alias}:AllLayer":
            continue
        try:
            day = date.fromisoformat(str(row.get("date"))[:10])
        except (ValueError, TypeError):
            continue
        if start <= day <= end:
            daily[(alias, day)].append(row)
    valid = {}
    for key, rows in daily.items():
        if len(rows) != 1:
            continue
        try:
            oil, water = float(rows[0]["OIL"]), float(rows[0]["WATER"])
        except (ValueError, TypeError, KeyError):
            continue
        if not all(isfinite(v) and v >= 0 for v in (oil, water)) or oil + water <= 0:
            continue
        valid[key] = (100 * water / (oil + water), oil, water)
    results = {}
    for alias in allowed:
        baseline = [v[0] for (a, d), v in valid.items() if a == alias and start <= d < end]
        current = valid.get((alias, end))
        result = {"Baseline Days": len(baseline), "WC Status": "Insufficient baseline",
                  "severity": None}
        if current is None:
            result["WC Status"] = "Invalid or missing current production"
        elif len(baseline) >= MIN_VALID_DAYS:
            avg, sigma = mean(baseline), stdev(baseline)
            effective = max(sigma, SIGMA_FLOOR_PP)
            departure = current[0] - avg
            score = departure / effective
            severity = "Warning" if score > 3 + 1e-9 else "Watch" if score > 2 + 1e-9 else None
            prior = valid.get((alias, end - timedelta(days=1)))
            result.update({
                "WC Status": "Assessed", "severity": severity,
                "Water Cut %": current[0], "WC Mean %": avg,
                "WC Std Dev (pp)": sigma, "WC Effective Sigma (pp)": effective,
                "WC Score": score,
                "WC Watch Limit %": avg + 2 * effective,
                "WC Warning Limit %": avg + 3 * effective,
                "Water Change": current[2] - prior[2] if prior else None,
            })
        results[alias] = result
    return results
