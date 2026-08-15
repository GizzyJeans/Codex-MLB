# Prospective validation report

- Prediction chain: **valid**, 24 records
- Settlement chain: **valid**, 24 records
- Settled game snapshots: **24**

## Forecast accuracy by snapshot

Win-probability Brier and log loss compare only games that have both model and pregame market probabilities.

| Snapshot | Games | Model total MAE | Pregame market MAE | Closing market MAE | Model bias | Model Brier | Market Brier | Model winner accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| initial | 24 | 3.10 | 3.17 | — | -0.50 | 0.276 | 0.252 | 45.8% |

initial log loss — model: 0.748, market: 0.696.

## Decision performance

Shadow ROI treats every recorded candidate as a one-unit wager. Actual ROI uses only recorded stake units.

| Classification | Bets | W-L-P/partial | Shadow PnL | Shadow ROI | Actual stake | Actual PnL | Actual ROI | Avg line CLV | Avg price CLV | Avg probability CLV |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CONDITIONAL | 2 | 1-1-0/0 | 0.10 | 5.0% | 0.00 | 0.00 | — | — | — | — |
| CONFLICT | 11 | 5-6-0/0 | -2.45 | -22.3% | 0.00 | 0.00 | — | — | — | — |
| WATCH | 5 | 3-2-0/0 | 0.49 | 9.8% | 0.00 | 0.00 | — | — | — | — |
