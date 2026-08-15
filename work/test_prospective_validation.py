import csv
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prospective_validation as validation


NOW = datetime(2026, 8, 12, 1, 0, tzinfo=timezone.utc)
AFTER_GAME = datetime(2026, 8, 13, 6, 0, tzinfo=timezone.utc)


class ProspectiveValidationTests(unittest.TestCase):
    def prediction_row(self, **updates):
        row = {field: "" for field in validation.PREDICTION_INPUT_FIELDS}
        row.update(
            {
                "snapshot_label": "initial",
                "source_timestamp_utc": "2026-08-12T00:00:00Z",
                "game_date": "2026-08-13",
                "game_pk": "12345",
                "first_pitch_utc": "2026-08-13T02:00:00Z",
                "away": "PHI",
                "home": "STL",
                "away_starter": "Pitcher A",
                "home_starter": "Pitcher B",
                "lineup_status": "projected",
                "model_version": "test-v1",
                "away_mu": "4.7",
                "home_mu": "3.8",
                "market_total": "8.0",
                "model_away_win_probability": "0.57",
                "market_away_win_probability": "0.53",
                "market": "total",
                "selection": "OVER",
                "line_value": "8",
                "line_kind": "plus",
                "tail_fraction": "0.5",
                "hk_price": "0.94",
                "selection_probability": "0.60",
                "selection_market_probability": "0.515",
                "base_ev": "0.10",
                "stress_ev": "0.02",
                "market_gap": "0.015",
                "classification": "FORMAL",
                "wager_id": "20260813-PHI-STL-O8P50",
                "stake_units": "1",
                "market_reference": "test screenshot",
                "notes": "fixture",
            }
        )
        row.update(updates)
        return row

    def result_row(self, **updates):
        row = {field: "" for field in validation.RESULT_INPUT_FIELDS}
        row.update(
            {
                "game_date": "2026-08-13",
                "away": "PHI",
                "home": "STL",
                "away_score": "5",
                "home_score": "3",
                "closing_total": "8.5",
                "closing_away_win_probability": "0.55",
                "closing_line": "8.5",
                "closing_hk_price": "0.90",
                "closing_selection_probability": "0.54",
                "result_source": "official fixture",
                "notes": "",
            }
        )
        row.update(updates)
        return row

    def write_csv(self, path, fields, rows):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_rejects_retrospective_prediction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "prediction.csv"
            self.write_csv(
                source,
                validation.PREDICTION_INPUT_FIELDS,
                [self.prediction_row(first_pitch_utc="2026-08-11T02:00:00Z")],
            )
            with self.assertRaisesRegex(validation.ValidationError, "retrospective"):
                validation.record_predictions(source, root / "predictions.jsonl", NOW)

    def test_enforces_taiwan_date_and_formal_stake_policy(self):
        with self.assertRaisesRegex(validation.ValidationError, "Taiwan date"):
            validation.normalize_prediction(
                self.prediction_row(game_date="2026-08-12"), NOW
            )
        with self.assertRaisesRegex(validation.ValidationError, "only FORMAL"):
            validation.normalize_prediction(
                self.prediction_row(classification="WATCH"), NOW
            )

    def test_allows_missing_moneyline_market_baseline(self):
        normalized = validation.normalize_prediction(
            self.prediction_row(market_away_win_probability=""), NOW
        )
        self.assertIsNone(normalized["market_away_win_probability"])

    def test_hash_chain_detects_a_changed_prediction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "prediction.csv"
            ledger = root / "predictions.jsonl"
            self.write_csv(
                source, validation.PREDICTION_INPUT_FIELDS, [self.prediction_row()]
            )
            validation.record_predictions(source, ledger, NOW)
            record = json.loads(ledger.read_text(encoding="utf-8"))
            record["away_mu"] = 9.9
            ledger.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validation.ValidationError, "hash verification"):
                validation.read_chain(ledger, "prediction")

    def test_taiwan_total_tail_settlement(self):
        base = {
            "market": "total",
            "selection": "OVER",
            "line_value": 8.0,
            "line_kind": "plus",
            "tail_fraction": 0.7,
        }
        self.assertEqual(
            validation.settlement_fractions(base, 5, 3),
            (0.7, 0.0, 0.3, "PARTIAL_WIN"),
        )
        base.update(selection="UNDER")
        self.assertEqual(
            validation.settlement_fractions(base, 5, 3),
            (0.0, 0.7, 0.3, "PARTIAL_LOSS"),
        )
        base.update(line_value=8.0, line_kind="minus", tail_fraction=0.3)
        self.assertEqual(
            validation.settlement_fractions(base, 5, 3),
            (0.3, 0.0, 0.7, "PARTIAL_WIN"),
        )
        self.assertEqual(
            validation.settlement_fractions(base, 6, 3),
            (0.0, 1.0, 0.0, "LOSS"),
        )
        self.assertEqual(
            validation.settlement_fractions(base, 4, 3),
            (1.0, 0.0, 0.0, "WIN"),
        )

    def test_run_line_tail_settlement(self):
        prediction = {
            "market": "run_line",
            "selection": "PHI",
            "away": "PHI",
            "home": "STL",
            "line_value": -1.0,
            "line_kind": "minus",
            "tail_fraction": 0.75,
        }
        self.assertEqual(
            validation.settlement_fractions(prediction, 5, 4),
            (0.0, 0.75, 0.25, "PARTIAL_LOSS"),
        )

    def test_end_to_end_record_settle_verify_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prediction_csv = root / "prediction.csv"
            result_csv = root / "result.csv"
            prediction_log = root / "predictions.jsonl"
            settlement_log = root / "settlements.jsonl"
            self.write_csv(
                prediction_csv,
                validation.PREDICTION_INPUT_FIELDS,
                [self.prediction_row()],
            )
            recorded = validation.record_predictions(
                prediction_csv, prediction_log, NOW
            )
            self.assertEqual(len(recorded), 1)

            # Deliberately omit game_pk to verify the date/team fallback match.
            self.write_csv(
                result_csv,
                validation.RESULT_INPUT_FIELDS,
                [self.result_row(game_pk="")],
            )
            settled = validation.settle_predictions(
                result_csv, prediction_log, settlement_log, AFTER_GAME
            )
            self.assertEqual(settled[0]["outcome"], "PARTIAL_WIN")
            self.assertAlmostEqual(settled[0]["shadow_pnl_units"], 0.47)
            self.assertEqual(len(validation.read_chain(prediction_log, "prediction")), 1)
            self.assertEqual(len(validation.read_chain(settlement_log, "settlement")), 1)

            report = validation.build_report(prediction_log, settlement_log)
            self.assertIn("| initial | 1 | 0.50 | 0.00 | 0.50 |", report)
            self.assertIn("| FORMAL | 1 | 0-0-0/1 | 0.47 |", report)
            self.assertIn("compare only games that have both model and pregame market", report)

            settlement = json.loads(settlement_log.read_text(encoding="utf-8"))
            settlement["prediction_hash"] = "f" * 64
            settlement["record_hash"] = validation.calculate_hash(settlement)
            settlement_log.write_text(
                json.dumps(settlement) + "\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(validation.ValidationError, "missing or changed"):
                validation.verify_ledgers(prediction_log, settlement_log)


if __name__ == "__main__":
    unittest.main()
