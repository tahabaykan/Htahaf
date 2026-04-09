# Greatest MM Scoring Logic

The Greatest MM engine calculates scores for Long and Short positions based on distances between market prices and recent trades.

## Core Metrics
- **Son5Tick**: The average of the last 5 "truth" ticks (filtered trades).
- **TruthTick (New Print)**: The single latest verified "truth" tick.
- **Ucuzluk (Cheapness)**: `(Bid - PrevClose) / PrevClose - BenchmarkChg`
- **Pahalılık (Expensiveness)**: `(Ask - PrevClose) / PrevClose - BenchmarkChg`

## Scoring Formulas

### MM Long Score
`MM Long = 200 * b_long + 4 * (b_long / a_long) - 50 * Ucuzluk`

- **b_long**: Distance from Son5Tick to Entry Point.
- **a_long**: Distance from Son5Tick to Bid.

### MM Short Score
`MM Short = 200 * a_short + 4 * (a_short / b_short) + 50 * Pahalılık`

- **a_short**: Distance from Son5Tick to Entry Point.
- **b_short**: Distance from Son5Tick to Ask.

## Scenarios
The engine evaluates 4 scenarios based on how `new_print` and `son5_tick` relate to current prices:

1.  **ORIGINAL**: Baseline distance calculation.
2.  **NEW_SON5**: Heavily weights the Son5Tick average.
3.  **NEW_ENTRY**: Weights the latest TruthTick as the entry anchor.
4.  **BOTH_NEW**: Uses both Son5 and TruthTick for maximum precision.

## Thresholds
- **MIN_SCORE**: 30.0 (Proposals below this are filtered out).
- **MAX_SCORE**: 250.0 (Proposals above this are considered extreme/outliers).
- **MIN_SPREAD**: 0.06 (Orders are only placed if spread is wide enough).
