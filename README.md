# Codex MLB Quant Analysis

This repository contains the model scripts and data files produced during the Codex MLB run-line and full-game total analysis chat.

## Contents

- `work/mlb_distribution_model.py` — full-game score and margin distribution model.
- `work/mlb_aug09_fundamentals.py` — August 9 fundamental run-mean model.
- `work/mlb_aug09_distribution.py` — August 9 simulation and market-probability calculations.
- `work/*.csv` — Statcast and team-level input data used by the analysis.

## Selection policy

`work/mlb_distribution_model.py` applies a robustness gate before a model edge
can be labelled `FORMAL`:

- Full-game totals require at least 6% base EV and non-negative EV after an
  adverse 0.3-run move in the projected game total.
- Run lines require at least 4% base EV, non-negative EV after reducing the
  backed team's run mean by 0.4, and no more than a four-percentage-point gap
  from the de-vigged public consensus.
- Positive edges that fail robustness are `WATCH` or `CONDITIONAL`; large
  market disagreements are explicitly labelled `CONFLICT`.

Run `python -m unittest work/test_mlb_distribution_model.py` to verify the
selection gates, including regression cases for the August 10 review.

Betting analysis is informational only and does not place wagers automatically.
