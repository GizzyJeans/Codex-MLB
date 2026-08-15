import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mlb_distribution_model as model


class SelectionPolicyTests(unittest.TestCase):
    def total_case(self, away_mu, home_mu, line, side, hk=0.94):
        base = model.total_metrics(
            model.final_score_dist(away_mu, home_mu), line, side, hk
        )
        stress = model.stressed_total_metrics(
            away_mu, home_mu, line, side, hk
        )
        return base, stress

    def test_tex_angels_over_is_demoted_to_watch(self):
        base, stress = self.total_case(5.0, 3.5, (8, "flat", 0), "over")
        self.assertAlmostEqual(base["ev"], 0.046, delta=0.002)
        self.assertLess(stress["ev"], 0)
        self.assertEqual(model.classify_total_pick(base, stress), "WATCH")

    def test_royals_dodgers_under_is_demoted_to_watch(self):
        base, stress = self.total_case(3.0, 4.5, (8, "plus", 0.70), "under")
        self.assertAlmostEqual(base["ev"], 0.051, delta=0.002)
        self.assertLess(stress["ev"], 0)
        self.assertEqual(model.classify_total_pick(base, stress), "WATCH")

    def test_robust_total_can_still_be_formal(self):
        base, stress = self.total_case(2.76, 4.14, (8, "plus", 0.70), "under")
        self.assertGreaterEqual(base["ev"], model.TOTAL_FORMAL_MIN_EV)
        self.assertGreaterEqual(stress["ev"], model.TOTAL_WORST_CASE_MIN_EV)
        self.assertEqual(model.classify_total_pick(base, stress), "FORMAL")

    def test_large_public_market_gap_is_conflict(self):
        base = {"ev": 0.10, "gap": 0.08}
        stress = {"ev": 0.03}
        self.assertEqual(model.classify_side_pick(base, stress), "CONFLICT")

    def test_non_robust_side_is_conditional(self):
        base = {"ev": 0.08, "gap": 0.02}
        stress = {"ev": -0.01}
        self.assertEqual(model.classify_side_pick(base, stress), "CONDITIONAL")


if __name__ == "__main__":
    unittest.main()
