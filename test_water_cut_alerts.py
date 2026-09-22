import unittest
from datetime import date, timedelta
from water_cut_alerts import assess_water_cut

class WaterCutTests(unittest.TestCase):
    def rows(self, current=95.4, n=30):
        end = date(2026, 9, 22)
        rows = [{"ALIAS": "M-07", "UNIQUEID": "M-07:AllLayer",
                 "date": str(end-timedelta(days=i)), "OIL": 5, "WATER": 95}
                for i in range(1, n+1)]
        rows.append({"ALIAS": "M-07", "UNIQUEID": "M-07:AllLayer",
                     "date": str(end), "OIL": 100-current, "WATER": current})
        return rows
    def assess(self, rows):
        return assess_water_cut(rows, "2026-09-22", ["M-07"])["M-07"]
    def test_floor_and_thresholds(self):
        self.assertEqual(self.assess(self.rows(95.4))["severity"], "Warning")
        self.assertEqual(self.assess(self.rows(95.25))["severity"], "Watch")
        self.assertIsNone(self.assess(self.rows(95.2))["severity"])
        self.assertIsNone(self.assess(self.rows(94))["severity"])
    def test_minimum_days(self):
        self.assertIsNone(self.assess(self.rows(n=19))["severity"])
        self.assertEqual(self.assess(self.rows(n=20))["severity"], "Warning")
    def test_today_future_and_old_days_excluded(self):
        rows = self.rows()
        rows += [dict(rows[-1], date="2026-09-23"), dict(rows[-1], date="2026-08-22")]
        result = self.assess(rows)
        self.assertEqual(result["Baseline Days"], 30)
        self.assertEqual(result["WC Mean %"], 95)
    def test_invalid_zero_duplicate_and_tubing_excluded(self):
        rows = self.rows(n=20)
        rows[0]["OIL"] = None
        rows.append(dict(rows[1]))
        rows.append(dict(rows[2], UNIQUEID="M-07:Tubing"))
        result = self.assess(rows)
        self.assertEqual(result["Baseline Days"], 18)
        self.assertIsNone(result["severity"])
        rows = self.rows()
        rows[-1].update(OIL=0, WATER=0)
        self.assertEqual(self.assess(rows)["WC Status"], "Invalid or missing current production")
    def test_sample_sigma_and_field_scope(self):
        rows = self.rows(97.2)
        for i, row in enumerate(rows[:-1]):
            wc = 94 if i % 2 else 96
            row.update(OIL=100-wc, WATER=wc)
        result = self.assess(rows)
        self.assertAlmostEqual(result["WC Std Dev (pp)"], (30/29)**0.5)
        self.assertEqual(result["severity"], "Watch")
        self.assertEqual(assess_water_cut(rows, "2026-09-22", ["M-08"])["M-08"]["Baseline Days"], 0)

if __name__ == "__main__":
    unittest.main()
