import unittest
import pandas as pd
import numpy as np
from decline_review import build_review, report_html


def fixture():
    dates = pd.date_range('2026-08-03', periods=28)
    rows = []
    for i, day in enumerate(dates):
        for alias, oil in [('M-01', 100 if i < 14 else 80), ('M-02', 50 if i < 14 else 60)]:
            rows.append(dict(date=day, ALIAS=alias, UNIQUEID=alias+':AllLayer', OIL=oil, WATER=100))
        rows.append(dict(date=day, ALIAS='M-01T', UNIQUEID='M-01:Tubing', OIL=999, WATER=999))
        rows.append(dict(date=day, ALIAS='M-01C', UNIQUEID='M-01C:AllLayer', OIL=999, WATER=999))
    trend = pd.DataFrame({'date': dates, 'reported_total': [200]*14+[180]*14})
    locations = pd.DataFrame({'ALIAS':['M-01','M-02'], 'field':['A','B'], 'status':['Oil Well','Oil Well']})
    return pd.DataFrame(rows), trend, locations


class ReviewTests(unittest.TestCase):
    def review(self, raw=None, trend=None, field='All', end='2026-08-30'):
        r, t, loc = fixture()
        return build_review(r if raw is None else raw, t if trend is None else trend, loc, end, field)

    def test_two_periods_and_net_contributors(self):
        r = self.review()
        self.assertEqual(r['expected_wells'], 2)
        self.assertEqual(r['summary']['Total Production (AH2)']['shortfall'], 280)
        self.assertEqual(r['summary']['Per-well oil (AllLayer)']['change'], -10)
        self.assertEqual(r['wells']['Change BOPD'].sum(), -10)
        self.assertEqual(r['wells'].Well.tolist(), ['M-01','M-02'])

    def test_missing_day_not_zero(self):
        raw, trend, _ = fixture()
        raw = raw[raw.date.ne(pd.Timestamp('2026-08-20'))]
        r = self.review(raw)
        self.assertTrue(pd.isna(r['daily'].loc['2026-08-20', 'well_oil']))
        self.assertTrue(pd.isna(r['summary']['Per-well oil (AllLayer)']['shortfall']))
        self.assertTrue(r['wells']['Change BOPD'].isna().all())

    def test_missing_ah2_no_fallback_to_well_oil(self):
        _, trend, _ = fixture()
        trend.loc[20,'reported_total'] = None
        r = self.review(trend=trend)
        self.assertEqual(r['summary']['Total Production (AH2)']['current_days'],13)
        self.assertTrue(pd.isna(r['summary']['Total Production (AH2)']['shortfall']))
        self.assertTrue(r['summary']['Per-well oil (AllLayer)']['complete'])

    def test_field_filter_and_no_field_ah2(self):
        r = self.review(field='A')
        self.assertNotIn('Total Production (AH2)',r['summary'])
        self.assertEqual(r['summary']['Per-well oil (AllLayer)']['change'],-20)
        self.assertEqual(len(r['wells']),1)

    def test_endpoint_does_not_use_future(self):
        r = self.review(end='2026-08-20')
        self.assertEqual(r['end'],pd.Timestamp('2026-08-20'))
        self.assertEqual(r['daily'].index.max(),pd.Timestamp('2026-08-20'))

    def test_incomplete_latest_day_rolls_back(self):
        raw, _, _ = fixture()
        raw.loc[raw.date.eq(pd.Timestamp('2026-08-30')) & raw.ALIAS.eq('M-01'), 'OIL'] = None
        self.assertEqual(self.review(raw)['end'],pd.Timestamp('2026-08-29'))

    def test_zero_baseline_and_true_zero(self):
        raw, _, _ = fixture()
        raw.loc[raw.ALIAS.eq('M-01'),'OIL'] = 0
        r = self.review(raw)
        one = r['wells'].set_index('Well').loc['M-01']
        self.assertTrue(pd.isna(one['Change %']))
        self.assertFalse(one['Latest zero'])
        self.assertEqual(one['Current days'],14)

    def test_duplicates_invalidated(self):
        raw, _, _ = fixture()
        raw = pd.concat([raw,raw.iloc[[0]]],ignore_index=True)
        r = self.review(raw)
        self.assertTrue(pd.isna(r['daily'].iloc[0].well_oil))
        self.assertTrue(any('Duplicate' in x for x in r['warnings']))

    def test_html_escapes_notes(self):
        report = report_html(self.review(), 'Total Production (AH2)',pd.DataFrame({'Action':['<script>alert(1)</script>']}),pd.DataFrame())
        self.assertNotIn('<script>', report)
        self.assertIn('&lt;script&gt;',report)
        self.assertIn('<svg',report)

    def test_empty_field(self):
        with self.assertRaises(ValueError):
            self.review(field='Unknown')

    def test_weighted_water_cut_and_repeated_flag(self):
        r=self.review()
        one=r['wells'].set_index('Well').loc['M-01']
        self.assertAlmostEqual(one['WC change (pp)'],100/180*100-50)
        self.assertTrue(one['Repeated last 7 days'])


if __name__ == '__main__':
    unittest.main()

