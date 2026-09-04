import unittest

import pandas as pd

from monthly_reconciliation import loss_segment_frame, reconciliation_components


class MonthlyReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.august = pd.Series(
            {
                "field_production_bbl": 26456.181487,
                "bsa_transfer_bbl": 14185.428880,
                "bsb_transfer_bbl": 11317.394130,
                "bsa_storage_loss_gain_bbl": -1273.905018,
                "bsb_storage_loss_gain_bbl": -1.629887,
                "bsa_stock_movement_bbl": -327.752026,
                "bsb_stock_movement_bbl": 5.575598,
                "sta_received_bbl": 24502.767768,
                "sta_transfer_bbl": 24470.162759,
                "sta_storage_loss_gain_bbl": -0.004009,
                "sta_stock_movement_bbl": 32.601,
                "bajubang_received_bbl": 24462.787,
                "bajubang_pumped_bbl": 24465.925,
                "bajubang_storage_loss_gain_bbl": -9.759,
                "bajubang_stock_movement_bbl": -12.897,
                "shipping_received_bbl": 24293.537,
                "tempino_opening_stock_bbl": 395.822,
                "tempino_closing_stock_bbl": 705.846,
                "tempino_meter_gross_bbl": 23983.514,
                "tempino_storage_loss_gain_bbl": 0.001,
                "tempino_pumping_net_bbl": 23890.008,
                "s_gerong_pumped_bbl": 23890.008,
                "s_gerong_received_bbl": 23800.843,
            }
        )

    def test_august_transfer_losses(self):
        frame = loss_segment_frame(self.august).set_index("Segment")
        self.assertAlmostEqual(frame.loc["Block Stations → STA", "Magnitude (bbl)"], 1000.055242, places=3)
        self.assertAlmostEqual(frame.loc["Bajubang → Shipping Tank", "Magnitude (bbl)"], 172.388, places=3)
        self.assertAlmostEqual(frame.loc["Tempino → S. Gerong", "Magnitude (bbl)"], 89.165, places=3)

    def test_waterfall_reconciles_to_official_lifting(self):
        components = reconciliation_components(self.august)
        reconstructed = self.august["field_production_bbl"] - sum(value for _, value in components)
        self.assertAlmostEqual(reconstructed, self.august["s_gerong_received_bbl"], places=6)

    def test_loss_display_uses_positive_magnitude_for_loss(self):
        frame = loss_segment_frame(self.august)
        final_segment = frame[frame["Segment"].eq("Tempino → S. Gerong")].iloc[0]
        self.assertEqual(final_segment["Result"], "Loss")
        self.assertGreater(final_segment["Magnitude (bbl)"], 0)


if __name__ == "__main__":
    unittest.main()

