from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


SCHEMA_VERSION = 1
ZERO_HASH = "0" * 64
PREDICTION_LOG = Path("validation/predictions.jsonl")
SETTLEMENT_LOG = Path("validation/settlements.jsonl")

MARKETS = {"none", "moneyline", "run_line", "total"}
LINE_KINDS = {"none", "half", "flat", "plus", "minus"}
LINEUP_STATUSES = {"unknown", "projected", "mixed", "confirmed"}
CLASSIFICATIONS = {"FORMAL", "WATCH", "CONDITIONAL", "CONFLICT", "PASS"}
MAX_SINGLE_STAKE_UNITS = 1.0
MAX_DAILY_STAKE_UNITS = 5.0

PREDICTION_INPUT_FIELDS = [
    "snapshot_label",
    "source_timestamp_utc",
    "game_date",
    "game_pk",
    "first_pitch_utc",
    "away",
    "home",
    "away_starter",
    "home_starter",
    "lineup_status",
    "model_version",
    "away_mu",
    "home_mu",
    "market_total",
    "model_away_win_probability",
    "market_away_win_probability",
    "market",
    "selection",
    "line_value",
    "line_kind",
    "tail_fraction",
    "hk_price",
    "selection_probability",
    "selection_market_probability",
    "base_ev",
    "stress_ev",
    "market_gap",
    "classification",
    "wager_id",
    "stake_units",
    "market_reference",
    "notes",
]

RESULT_INPUT_FIELDS = [
    "prediction_id",
    "game_date",
    "game_pk",
    "away",
    "home",
    "away_score",
    "home_score",
    "closing_total",
    "closing_away_win_probability",
    "closing_line",
    "closing_hk_price",
    "closing_selection_probability",
    "result_source",
    "notes",
]


class ValidationError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_utc(value: str, field: str) -> datetime:
    text = value.strip()
    if not text:
        raise ValidationError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{field} must be an ISO-8601 timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise ValidationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def parse_date(value: str, field: str = "game_date") -> str:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValidationError(f"{field} must use YYYY-MM-DD: {value}") from exc


def text_value(row: dict[str, str], field: str, *, required: bool = False) -> str:
    value = (row.get(field) or "").strip()
    if required and not value:
        raise ValidationError(f"{field} is required")
    return value


def float_value(
    row: dict[str, str],
    field: str,
    *,
    required: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    value = text_value(row, field)
    if not value:
        if required:
            raise ValidationError(f"{field} is required")
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValidationError(f"{field} must be numeric: {value}") from exc
    if not math.isfinite(parsed):
        raise ValidationError(f"{field} must be finite")
    if minimum is not None and parsed < minimum:
        raise ValidationError(f"{field} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        raise ValidationError(f"{field} must be <= {maximum}")
    return parsed


def int_value(
    row: dict[str, str], field: str, *, required: bool = False, minimum: int | None = None
) -> int | None:
    value = text_value(row, field)
    if not value:
        if required:
            raise ValidationError(f"{field} is required")
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValidationError(f"{field} must be an integer: {value}") from exc
    if minimum is not None and parsed < minimum:
        raise ValidationError(f"{field} must be >= {minimum}")
    return parsed


def read_csv(path: Path, required_fields: Iterable[str]) -> list[dict[str, str]]:
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc
    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValidationError(f"{path} has no header")
        missing = [field for field in required_fields if field not in reader.fieldnames]
        if missing:
            raise ValidationError(f"{path} is missing columns: {', '.join(missing)}")
        rows = [dict(row) for row in reader]
    if not rows:
        raise ValidationError(f"{path} has no data rows")
    return rows


def canonical_json(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def calculate_hash(record: dict) -> str:
    payload = {key: value for key, value in record.items() if key != "record_hash"}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def read_chain(path: Path, record_type: str) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    previous_hash = ZERO_HASH
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValidationError(f"{path}:{line_number} is not valid JSON") from exc
            if record.get("record_type") != record_type:
                raise ValidationError(f"{path}:{line_number} has the wrong record_type")
            if record.get("schema_version") != SCHEMA_VERSION:
                raise ValidationError(f"{path}:{line_number} has an unsupported schema_version")
            if record.get("sequence") != len(records) + 1:
                raise ValidationError(f"{path}:{line_number} has a broken sequence")
            if record.get("previous_hash") != previous_hash:
                raise ValidationError(f"{path}:{line_number} has a broken previous_hash")
            expected = calculate_hash(record)
            if record.get("record_hash") != expected:
                raise ValidationError(f"{path}:{line_number} hash verification failed")
            previous_hash = expected
            records.append(record)
    return records


def append_chain(path: Path, records: list[dict]) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(canonical_json(record) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def verify_ledgers(
    prediction_path: Path, settlement_path: Path
) -> tuple[list[dict], list[dict]]:
    predictions = read_chain(prediction_path, "prediction")
    settlements = read_chain(settlement_path, "settlement")
    prediction_by_id: dict[str, dict] = {}
    for prediction in predictions:
        prediction_id = prediction.get("prediction_id")
        if not prediction_id or prediction_id in prediction_by_id:
            raise ValidationError("prediction ledger contains a missing or duplicate ID")
        prediction_by_id[prediction_id] = prediction

    settlement_ids: set[str] = set()
    settled_prediction_ids: set[str] = set()
    for settlement in settlements:
        settlement_id = settlement.get("settlement_id")
        prediction_id = settlement.get("prediction_id")
        if not settlement_id or settlement_id in settlement_ids:
            raise ValidationError("settlement ledger contains a missing or duplicate ID")
        settlement_ids.add(settlement_id)
        if not prediction_id or prediction_id in settled_prediction_ids:
            raise ValidationError("a prediction has a missing or duplicate settlement")
        settled_prediction_ids.add(prediction_id)
        prediction = prediction_by_id.get(prediction_id)
        if prediction is None or prediction["record_hash"] != settlement.get(
            "prediction_hash"
        ):
            raise ValidationError("settlement points to a missing or changed prediction")
    return predictions, settlements


def game_key(record: dict) -> str:
    if record.get("game_pk"):
        return f"pk:{record['game_pk']}"
    return f"{record['game_date']}:{record['away']}@{record['home']}"


def prediction_game_keys(record: dict) -> list[str]:
    keys = []
    if record.get("game_pk"):
        keys.append(f"pk:{record['game_pk']}")
    keys.append(f"{record['game_date']}:{record['away']}@{record['home']}")
    return keys


def prediction_identity(record: dict) -> tuple:
    return (
        game_key(record),
        record["snapshot_label"],
        record["market"],
        record["selection"],
        record.get("line_value"),
        record["line_kind"],
        record["tail_fraction"],
    )


def normalize_prediction(row: dict[str, str], now: datetime) -> dict:
    snapshot_label = text_value(row, "snapshot_label", required=True).lower()
    source_time = parse_utc(text_value(row, "source_timestamp_utc", required=True), "source_timestamp_utc")
    first_pitch = parse_utc(text_value(row, "first_pitch_utc", required=True), "first_pitch_utc")
    if first_pitch <= now:
        raise ValidationError("first_pitch_utc must be in the future; retrospective rows are prohibited")
    if source_time >= first_pitch:
        raise ValidationError("source_timestamp_utc must be before first_pitch_utc")
    if source_time > now:
        raise ValidationError("source_timestamp_utc cannot be in the future")

    game_date = parse_date(text_value(row, "game_date", required=True))
    taiwan_game_date = (first_pitch + timedelta(hours=8)).date().isoformat()
    if game_date != taiwan_game_date:
        raise ValidationError(
            f"game_date must be the Taiwan date of first pitch: {taiwan_game_date}"
        )

    away = text_value(row, "away", required=True).upper()
    home = text_value(row, "home", required=True).upper()
    if away == home:
        raise ValidationError("away and home teams must differ")

    lineup_status = text_value(row, "lineup_status", required=True).lower()
    if lineup_status not in LINEUP_STATUSES:
        raise ValidationError(f"unsupported lineup_status: {lineup_status}")
    classification = text_value(row, "classification", required=True).upper()
    if classification not in CLASSIFICATIONS:
        raise ValidationError(f"unsupported classification: {classification}")
    market = text_value(row, "market", required=True).lower()
    if market not in MARKETS:
        raise ValidationError(f"unsupported market: {market}")
    selection = text_value(row, "selection", required=True).upper()
    line_kind = text_value(row, "line_kind", required=True).lower()
    if line_kind not in LINE_KINDS:
        raise ValidationError(f"unsupported line_kind: {line_kind}")

    line_value = float_value(row, "line_value")
    tail_fraction = float_value(
        row, "tail_fraction", required=True, minimum=0.0, maximum=1.0
    )
    hk_price = float_value(row, "hk_price", required=True, minimum=0.0)
    stake_units = float_value(row, "stake_units", required=True, minimum=0.0)
    wager_id = text_value(row, "wager_id")

    if market == "none":
        if selection != "NONE" or line_kind != "none" or line_value is not None:
            raise ValidationError("market=none requires selection=NONE, line_kind=none and blank line_value")
        if hk_price != 0 or tail_fraction != 0 or stake_units != 0:
            raise ValidationError("market=none requires zero price, tail_fraction and stake")
        if classification != "PASS":
            raise ValidationError("market=none requires classification=PASS")
    elif market == "total":
        if selection not in {"OVER", "UNDER"}:
            raise ValidationError("total selection must be OVER or UNDER")
        if line_value is None or line_value <= 0:
            raise ValidationError("total line_value must be positive")
        if line_kind == "none":
            raise ValidationError("total requires a settlement line_kind")
    elif market in {"moneyline", "run_line"}:
        if selection not in {away, home}:
            raise ValidationError(f"{market} selection must equal away or home team")
        if market == "moneyline":
            if line_value is not None or line_kind != "none" or tail_fraction != 0:
                raise ValidationError("moneyline requires blank line_value, line_kind=none and zero tail_fraction")
        elif line_value is None or line_kind == "none":
            raise ValidationError("run_line requires line_value and a settlement line_kind")

    if market != "none" and hk_price <= 0:
        raise ValidationError("a wager market requires hk_price > 0")
    if stake_units > MAX_SINGLE_STAKE_UNITS:
        raise ValidationError(
            f"stake_units exceeds the {MAX_SINGLE_STAKE_UNITS:g}-unit single-bet cap"
        )
    if stake_units > 0 and classification != "FORMAL":
        raise ValidationError("only FORMAL selections may have a positive stake")
    if bool(wager_id) != (stake_units > 0):
        raise ValidationError("wager_id is required exactly when stake_units is positive")
    if line_kind in {"plus", "minus"} and not 0 < tail_fraction <= 1:
        raise ValidationError("plus/minus lines require tail_fraction in (0, 1]")
    if line_kind in {"none", "half", "flat"} and tail_fraction != 0:
        raise ValidationError(f"line_kind={line_kind} requires tail_fraction=0")

    selection_probability = float_value(
        row, "selection_probability", minimum=0.0, maximum=1.0
    )
    selection_market_probability = float_value(
        row, "selection_market_probability", minimum=0.0, maximum=1.0
    )
    if market != "none" and (
        selection_probability is None or selection_market_probability is None
    ):
        raise ValidationError("wager rows require selection and market probabilities")

    return {
        "snapshot_label": snapshot_label,
        "source_timestamp_utc": iso_utc(source_time),
        "game_date": game_date,
        "game_pk": text_value(row, "game_pk"),
        "first_pitch_utc": iso_utc(first_pitch),
        "away": away,
        "home": home,
        "away_starter": text_value(row, "away_starter", required=True),
        "home_starter": text_value(row, "home_starter", required=True),
        "lineup_status": lineup_status,
        "model_version": text_value(row, "model_version", required=True),
        "away_mu": float_value(row, "away_mu", required=True, minimum=0.0),
        "home_mu": float_value(row, "home_mu", required=True, minimum=0.0),
        "market_total": float_value(row, "market_total", required=True, minimum=0.1),
        "model_away_win_probability": float_value(
            row, "model_away_win_probability", required=True, minimum=0.0, maximum=1.0
        ),
        "market_away_win_probability": float_value(
            row, "market_away_win_probability", minimum=0.0, maximum=1.0
        ),
        "market": market,
        "selection": selection,
        "line_value": line_value,
        "line_kind": line_kind,
        "tail_fraction": tail_fraction,
        "hk_price": hk_price,
        "selection_probability": selection_probability,
        "selection_market_probability": selection_market_probability,
        "base_ev": float_value(row, "base_ev"),
        "stress_ev": float_value(row, "stress_ev"),
        "market_gap": float_value(row, "market_gap"),
        "classification": classification,
        "wager_id": wager_id,
        "stake_units": stake_units,
        "market_reference": text_value(row, "market_reference", required=True),
        "notes": text_value(row, "notes"),
    }


GAME_SNAPSHOT_FIELDS = (
    "first_pitch_utc",
    "away",
    "home",
    "away_starter",
    "home_starter",
    "lineup_status",
    "model_version",
    "away_mu",
    "home_mu",
    "market_total",
    "model_away_win_probability",
    "market_away_win_probability",
)


def validate_snapshot_consistency(rows: list[dict]) -> None:
    grouped: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (game_key(row), row["snapshot_label"])
        if key not in grouped:
            grouped[key] = row
            continue
        reference = grouped[key]
        inconsistent = [field for field in GAME_SNAPSHOT_FIELDS if row[field] != reference[field]]
        if inconsistent:
            raise ValidationError(
                f"inconsistent game snapshot {key}: {', '.join(inconsistent)}"
            )


def record_predictions(input_path: Path, log_path: Path, now: datetime | None = None) -> list[dict]:
    current_time = (now or utc_now()).astimezone(timezone.utc)
    existing = read_chain(log_path, "prediction")
    rows = read_csv(input_path, PREDICTION_INPUT_FIELDS)
    normalized: list[dict] = []
    for row_number, row in enumerate(rows, start=2):
        try:
            normalized.append(normalize_prediction(row, current_time))
        except ValidationError as exc:
            raise ValidationError(f"{input_path}:{row_number}: {exc}") from exc
    validate_snapshot_consistency(normalized)

    existing_identities = {prediction_identity(record) for record in existing}
    existing_wager_ids = {
        record["wager_id"] for record in existing if record.get("wager_id")
    }
    new_identities: set[tuple] = set()
    new_wager_ids: set[str] = set()
    daily_stakes: dict[str, float] = defaultdict(float)
    for record in existing:
        daily_stakes[record["game_date"]] += record["stake_units"]
    for row in normalized:
        identity = prediction_identity(row)
        if identity in existing_identities or identity in new_identities:
            raise ValidationError(f"duplicate prediction identity: {identity}")
        new_identities.add(identity)
        if row["wager_id"]:
            if row["wager_id"] in existing_wager_ids or row["wager_id"] in new_wager_ids:
                raise ValidationError(f"duplicate wager_id: {row['wager_id']}")
            new_wager_ids.add(row["wager_id"])
        daily_stakes[row["game_date"]] += row["stake_units"]
        if daily_stakes[row["game_date"]] > MAX_DAILY_STAKE_UNITS + 1e-9:
            raise ValidationError(
                f"{row['game_date']} stake exceeds the "
                f"{MAX_DAILY_STAKE_UNITS:g}-unit daily cap"
            )

    batch_id = str(uuid.uuid4())
    previous_hash = existing[-1]["record_hash"] if existing else ZERO_HASH
    records: list[dict] = []
    for row in normalized:
        record = {
            "record_type": "prediction",
            "schema_version": SCHEMA_VERSION,
            "sequence": len(existing) + len(records) + 1,
            "prediction_id": str(uuid.uuid4()),
            "batch_id": batch_id,
            "recorded_at_utc": iso_utc(current_time),
            **row,
            "previous_hash": previous_hash,
        }
        record["record_hash"] = calculate_hash(record)
        previous_hash = record["record_hash"]
        records.append(record)
    append_chain(log_path, records)
    read_chain(log_path, "prediction")
    return records


def normalize_result(row: dict[str, str]) -> dict:
    away = text_value(row, "away").upper()
    home = text_value(row, "home").upper()
    result = {
        "prediction_id": text_value(row, "prediction_id"),
        "game_date": parse_date(text_value(row, "game_date", required=True)),
        "game_pk": text_value(row, "game_pk"),
        "away": away,
        "home": home,
        "away_score": int_value(row, "away_score", required=True, minimum=0),
        "home_score": int_value(row, "home_score", required=True, minimum=0),
        "closing_total": float_value(row, "closing_total", minimum=0.1),
        "closing_away_win_probability": float_value(
            row, "closing_away_win_probability", minimum=0.0, maximum=1.0
        ),
        "closing_line": float_value(row, "closing_line"),
        "closing_hk_price": float_value(row, "closing_hk_price", minimum=0.0),
        "closing_selection_probability": float_value(
            row, "closing_selection_probability", minimum=0.0, maximum=1.0
        ),
        "result_source": text_value(row, "result_source", required=True),
        "notes": text_value(row, "notes"),
    }
    if not result["prediction_id"] and not result["game_pk"] and (not away or not home):
        raise ValidationError("result requires prediction_id, game_pk, or both away and home")
    return result


def result_game_keys(result: dict) -> list[str]:
    keys = []
    if result["game_pk"]:
        keys.append(f"pk:{result['game_pk']}")
    if result["away"] and result["home"]:
        keys.append(f"{result['game_date']}:{result['away']}@{result['home']}")
    return keys


def settlement_fractions(prediction: dict, away_score: int, home_score: int) -> tuple[float, float, float, str]:
    market = prediction["market"]
    if market == "none":
        return 0.0, 0.0, 1.0, "NO_BET"
    if market == "moneyline":
        selected_score = away_score if prediction["selection"] == prediction["away"] else home_score
        opponent_score = home_score if prediction["selection"] == prediction["away"] else away_score
        if selected_score == opponent_score:
            raise ValidationError("moneyline game cannot be settled while tied")
        return (1.0, 0.0, 0.0, "WIN") if selected_score > opponent_score else (0.0, 1.0, 0.0, "LOSS")

    if market == "total":
        total_delta = away_score + home_score - prediction["line_value"]
        comparison = (
            total_delta if prediction["selection"] == "OVER" else -total_delta
        )
    else:
        selected_score = away_score if prediction["selection"] == prediction["away"] else home_score
        opponent_score = home_score if prediction["selection"] == prediction["away"] else away_score
        comparison = selected_score + prediction["line_value"] - opponent_score

    if comparison > 1e-9:
        return 1.0, 0.0, 0.0, "WIN"
    if comparison < -1e-9:
        return 0.0, 1.0, 0.0, "LOSS"

    kind = prediction["line_kind"]
    fraction = prediction["tail_fraction"]
    remainder = round(1.0 - fraction, 10)
    if kind == "flat":
        return 0.0, 0.0, 1.0, "PUSH"
    favorable_tail = kind == "plus"
    if market == "total" and prediction["selection"] == "UNDER":
        favorable_tail = kind == "minus"
    if favorable_tail:
        return fraction, 0.0, remainder, "PARTIAL_WIN"
    if kind in {"plus", "minus"}:
        return 0.0, fraction, remainder, "PARTIAL_LOSS"
    raise ValidationError("a half line unexpectedly landed exactly on its threshold")


def line_clv(prediction: dict, closing_line: float | None) -> float | None:
    if closing_line is None or prediction["line_value"] is None:
        return None
    if prediction["market"] == "total":
        if prediction["selection"] == "OVER":
            return closing_line - prediction["line_value"]
        return prediction["line_value"] - closing_line
    if prediction["market"] == "run_line":
        return prediction["line_value"] - closing_line
    return None


def settle_predictions(
    results_path: Path,
    prediction_path: Path,
    settlement_path: Path,
    now: datetime | None = None,
) -> list[dict]:
    current_time = (now or utc_now()).astimezone(timezone.utc)
    predictions, existing = verify_ledgers(prediction_path, settlement_path)
    if not predictions:
        raise ValidationError("prediction log is empty")
    settled_ids = {record["prediction_id"] for record in existing}
    result_rows = read_csv(results_path, RESULT_INPUT_FIELDS)
    results: list[dict] = []
    for row_number, row in enumerate(result_rows, start=2):
        try:
            results.append(normalize_result(row))
        except ValidationError as exc:
            raise ValidationError(f"{results_path}:{row_number}: {exc}") from exc

    prediction_ids = {prediction["prediction_id"] for prediction in predictions}
    by_prediction: dict[str, dict] = {}
    for row in results:
        prediction_id = row["prediction_id"]
        if not prediction_id:
            continue
        if prediction_id not in prediction_ids:
            raise ValidationError(f"unknown prediction_id in result: {prediction_id}")
        if prediction_id in by_prediction:
            raise ValidationError(f"duplicate prediction result: {prediction_id}")
        by_prediction[prediction_id] = row
    by_game: dict[str, dict] = {}
    for row in results:
        if row["prediction_id"]:
            continue
        for key in result_game_keys(row):
            if key in by_game:
                raise ValidationError(f"duplicate game result: {key}")
            by_game[key] = row

    previous_hash = existing[-1]["record_hash"] if existing else ZERO_HASH
    settlements: list[dict] = []
    for prediction in predictions:
        if prediction["prediction_id"] in settled_ids:
            continue
        result = by_prediction.get(prediction["prediction_id"])
        if result is None:
            result = next(
                (
                    by_game[key]
                    for key in prediction_game_keys(prediction)
                    if key in by_game
                ),
                None,
            )
        if result is None:
            continue
        if result["game_date"] != prediction["game_date"]:
            raise ValidationError(
                f"result date does not match prediction {prediction['prediction_id']}"
            )
        if result["away"] and result["away"] != prediction["away"]:
            raise ValidationError(
                f"away team does not match prediction {prediction['prediction_id']}"
            )
        if result["home"] and result["home"] != prediction["home"]:
            raise ValidationError(
                f"home team does not match prediction {prediction['prediction_id']}"
            )
        if current_time < parse_utc(prediction["first_pitch_utc"], "first_pitch_utc"):
            raise ValidationError(f"cannot settle {prediction['prediction_id']} before first pitch")
        win_fraction, loss_fraction, push_fraction, outcome = settlement_fractions(
            prediction, result["away_score"], result["home_score"]
        )
        shadow_pnl = win_fraction * prediction["hk_price"] - loss_fraction
        pnl_units = prediction["stake_units"] * shadow_pnl
        probability_clv = None
        if result["closing_selection_probability"] is not None and prediction["selection_market_probability"] is not None:
            probability_clv = (
                result["closing_selection_probability"]
                - prediction["selection_market_probability"]
            )
        price_clv = None
        if result["closing_hk_price"] is not None:
            price_clv = prediction["hk_price"] - result["closing_hk_price"]

        record = {
            "record_type": "settlement",
            "schema_version": SCHEMA_VERSION,
            "sequence": len(existing) + len(settlements) + 1,
            "settlement_id": str(uuid.uuid4()),
            "prediction_id": prediction["prediction_id"],
            "prediction_hash": prediction["record_hash"],
            "settled_at_utc": iso_utc(current_time),
            "game_date": prediction["game_date"],
            "game_pk": result["game_pk"] or prediction["game_pk"],
            "away": prediction["away"],
            "home": prediction["home"],
            "away_score": result["away_score"],
            "home_score": result["home_score"],
            "outcome": outcome,
            "win_fraction": win_fraction,
            "loss_fraction": loss_fraction,
            "push_fraction": push_fraction,
            "shadow_pnl_units": shadow_pnl,
            "stake_units": prediction["stake_units"],
            "pnl_units": pnl_units,
            "closing_total": result["closing_total"],
            "closing_away_win_probability": result["closing_away_win_probability"],
            "closing_line": result["closing_line"],
            "closing_hk_price": result["closing_hk_price"],
            "closing_selection_probability": result["closing_selection_probability"],
            "line_clv": line_clv(prediction, result["closing_line"]),
            "price_clv": price_clv,
            "probability_clv": probability_clv,
            "result_source": result["result_source"],
            "notes": result["notes"],
            "previous_hash": previous_hash,
        }
        record["record_hash"] = calculate_hash(record)
        previous_hash = record["record_hash"]
        settlements.append(record)
    if not settlements:
        raise ValidationError("no unsettled predictions matched the result rows")
    append_chain(settlement_path, settlements)
    read_chain(settlement_path, "settlement")
    return settlements


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def fmt_number(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def fmt_percent(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{100 * value:.{digits}f}%"


def brier(probability: float, actual: int) -> float:
    return (probability - actual) ** 2


def log_loss(probability: float, actual: int) -> float:
    probability = min(max(probability, 1e-9), 1 - 1e-9)
    return -(actual * math.log(probability) + (1 - actual) * math.log(1 - probability))


def build_report(prediction_path: Path, settlement_path: Path) -> str:
    predictions, settlements = verify_ledgers(prediction_path, settlement_path)
    settlement_by_prediction = {row["prediction_id"]: row for row in settlements}

    forecast_units: dict[tuple[str, str], dict] = {}
    for prediction in predictions:
        settlement = settlement_by_prediction.get(prediction["prediction_id"])
        if settlement is None:
            continue
        key = (game_key(prediction), prediction["snapshot_label"])
        forecast_units.setdefault(key, {"prediction": prediction, "settlement": settlement})

    by_snapshot: dict[str, list[dict]] = defaultdict(list)
    for unit in forecast_units.values():
        by_snapshot[unit["prediction"]["snapshot_label"]].append(unit)

    lines = [
        "# Prospective validation report",
        "",
        f"- Prediction chain: **valid**, {len(predictions)} records",
        f"- Settlement chain: **valid**, {len(settlements)} records",
        f"- Settled game snapshots: **{len(forecast_units)}**",
        "",
        "## Forecast accuracy by snapshot",
        "",
        "Win-probability Brier and log loss compare only games that have both model and pregame market probabilities.",
        "",
        "| Snapshot | Games | Model total MAE | Pregame market MAE | Closing market MAE | Model bias | Model Brier | Market Brier | Model winner accuracy |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, units in sorted(by_snapshot.items()):
        model_errors: list[float] = []
        market_errors: list[float] = []
        closing_errors: list[float] = []
        model_biases: list[float] = []
        model_briers: list[float] = []
        market_briers: list[float] = []
        model_log_losses: list[float] = []
        market_log_losses: list[float] = []
        model_correct = 0
        for unit in units:
            prediction = unit["prediction"]
            settlement = unit["settlement"]
            actual_total = settlement["away_score"] + settlement["home_score"]
            model_total = prediction["away_mu"] + prediction["home_mu"]
            model_errors.append(abs(model_total - actual_total))
            market_errors.append(abs(prediction["market_total"] - actual_total))
            model_biases.append(model_total - actual_total)
            if settlement["closing_total"] is not None:
                closing_errors.append(abs(settlement["closing_total"] - actual_total))
            away_won = int(settlement["away_score"] > settlement["home_score"])
            model_probability = prediction["model_away_win_probability"]
            market_probability = prediction["market_away_win_probability"]
            if market_probability is not None:
                model_briers.append(brier(model_probability, away_won))
                model_log_losses.append(log_loss(model_probability, away_won))
                market_briers.append(brier(market_probability, away_won))
                market_log_losses.append(log_loss(market_probability, away_won))
            model_correct += int((model_probability >= 0.5) == bool(away_won))
        lines.append(
            f"| {label} | {len(units)} | {fmt_number(mean(model_errors), 2)} | "
            f"{fmt_number(mean(market_errors), 2)} | {fmt_number(mean(closing_errors), 2)} | "
            f"{fmt_number(mean(model_biases), 2)} | {fmt_number(mean(model_briers), 3)} | "
            f"{fmt_number(mean(market_briers), 3)} | {fmt_percent(model_correct / len(units))} |"
        )
        lines.extend(
            [
                "",
                f"{label} log loss — model: {fmt_number(mean(model_log_losses), 3)}, "
                f"market: {fmt_number(mean(market_log_losses), 3)}.",
            ]
        )

    if not by_snapshot:
        lines.append("| — | 0 | — | — | — | — | — | — | — |")

    decision_rows = []
    for prediction in predictions:
        settlement = settlement_by_prediction.get(prediction["prediction_id"])
        if settlement is not None and prediction["market"] != "none":
            decision_rows.append((prediction, settlement))
    by_classification: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for row in decision_rows:
        by_classification[row[0]["classification"]].append(row)

    lines.extend(
        [
            "",
            "## Decision performance",
            "",
            "Shadow ROI treats every recorded candidate as a one-unit wager. Actual ROI uses only recorded stake units.",
            "",
            "| Classification | Bets | W-L-P/partial | Shadow PnL | Shadow ROI | Actual stake | Actual PnL | Actual ROI | Avg line CLV | Avg price CLV | Avg probability CLV |",
            "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for classification in sorted(by_classification):
        rows = by_classification[classification]
        full_wins = sum(row[1]["outcome"] == "WIN" for row in rows)
        full_losses = sum(row[1]["outcome"] == "LOSS" for row in rows)
        pushes = sum(row[1]["outcome"] == "PUSH" for row in rows)
        partials = sum(row[1]["outcome"].startswith("PARTIAL") for row in rows)
        shadow_pnl = sum(row[1]["shadow_pnl_units"] for row in rows)
        actual_stake = sum(row[1]["stake_units"] for row in rows)
        actual_pnl = sum(row[1]["pnl_units"] for row in rows)
        line_clvs = [
            row[1]["line_clv"] for row in rows if row[1]["line_clv"] is not None
        ]
        price_clvs = [
            row[1]["price_clv"] for row in rows if row[1]["price_clv"] is not None
        ]
        probability_clvs = [
            row[1]["probability_clv"]
            for row in rows
            if row[1]["probability_clv"] is not None
        ]
        lines.append(
            f"| {classification} | {len(rows)} | {full_wins}-{full_losses}-{pushes}/{partials} | "
            f"{shadow_pnl:.2f} | {fmt_percent(shadow_pnl / len(rows))} | "
            f"{actual_stake:.2f} | {actual_pnl:.2f} | "
            f"{fmt_percent(actual_pnl / actual_stake if actual_stake else None)} | "
            f"{fmt_number(mean(line_clvs), 2)} | "
            f"{fmt_number(mean(price_clvs), 3)} | "
            f"{fmt_percent(mean(probability_clvs))} |"
        )

    if not by_classification:
        lines.append("| — | 0 | — | — | — | — | — | — | — | — | — |")
    return "\n".join(lines) + "\n"


def write_report(report: str, output: Path | None) -> None:
    if output is None:
        print(report, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append-only prospective MLB model validation ledger"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record", help="append a pregame CSV snapshot")
    record.add_argument("--input", type=Path, required=True)
    record.add_argument("--predictions", type=Path, default=PREDICTION_LOG)

    settle = subparsers.add_parser("settle", help="append official game results")
    settle.add_argument("--input", type=Path, required=True)
    settle.add_argument("--predictions", type=Path, default=PREDICTION_LOG)
    settle.add_argument("--settlements", type=Path, default=SETTLEMENT_LOG)

    verify = subparsers.add_parser("verify", help="verify both hash chains")
    verify.add_argument("--predictions", type=Path, default=PREDICTION_LOG)
    verify.add_argument("--settlements", type=Path, default=SETTLEMENT_LOG)

    report = subparsers.add_parser("report", help="render a Markdown report")
    report.add_argument("--predictions", type=Path, default=PREDICTION_LOG)
    report.add_argument("--settlements", type=Path, default=SETTLEMENT_LOG)
    report.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "record":
            records = record_predictions(args.input, args.predictions)
            print(f"Recorded {len(records)} prospective predictions in batch {records[0]['batch_id']}")
            for record in records:
                print(f"{record['prediction_id']} {record['away']}@{record['home']} {record['classification']}")
        elif args.command == "settle":
            records = settle_predictions(
                args.input, args.predictions, args.settlements
            )
            print(f"Settled {len(records)} prediction records")
        elif args.command == "verify":
            predictions, settlements = verify_ledgers(
                args.predictions, args.settlements
            )
            print(
                f"Integrity OK: {len(predictions)} predictions, "
                f"{len(settlements)} settlements"
            )
        elif args.command == "report":
            write_report(
                build_report(args.predictions, args.settlements), args.output
            )
    except ValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
