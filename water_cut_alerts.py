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
    current_status = {}
    for (alias, day), rows in daily.items():
        if day != end:
            if len(rows) == 1:
                try:
                    oil, water = float(rows[0]["OIL"]), float(rows[0]["WATER"])
                    if all(isfinite(v) and v >= 0 for v in (oil, water)) and oil + water > 0:
                        valid[(alias, day)] = (100 * water / (oil + water), oil, water)
                except (ValueError, TypeError, KeyError):
                    pass
            continue
        if len(rows) > 1:
            current_status[alias] = "Duplicate records"
            continue
        try:
            oil, water = float(rows[0]["OIL"]), float(rows[0]["WATER"])
        except (ValueError, TypeError, KeyError):
            current_status[alias] = "Incomplete oil/water data"
            continue
        if not all(isfinite(v) and v >= 0 for v in (oil, water)):
            current_status[alias] = "Incomplete oil/water data"
        elif oil + water == 0:
            current_status[alias] = "No liquid production"
        else:
            valid[(alias, day)] = (100 * water / (oil + water), oil, water)
            current_status[alias] = "Current data valid"

    results = {}
    for alias in allowed:
        baseline = [v[0] for (a, d), v in valid.items() if a == alias and start <= d < end]
        current = valid.get((alias, end))
        result = {"Baseline Days": len(baseline),
                  "WC Status": current_status.get(alias, "Missing record"),
                  "severity": None}
        if current is not None:
            if len(baseline) < MIN_VALID_DAYS:
                result["WC Status"] = "Insufficient baseline"
            else:
                avg, sigma = mean(baseline), stdev(baseline)
                effective = max(sigma, SIGMA_FLOOR_PP)
                score = (current[0] - avg) / effective
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
