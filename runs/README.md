# Run log

Every hour a scheduled GitHub Action quotes every ticker on both venues
through the same code the live site runs (`scripts/record_run.py`) and
commits the full response here, one JSON line per venue per sweep, in
`runs/YYYY-MM-DD.jsonl` (UTC). The commit history is the timestamp.

Counts are ticker-quotes per verdict for each UTC day and venue. *Weekend
sweeps* were taken while the US cash market was closed for the weekend.

| Day (UTC) | Venue | Sweeps | Weekend sweeps | OK | LAGGED | STALE | NO_POOL | NO_REFERENCE | ERROR |
|---|---|---|---|---|---|---|---|---|---|
| 2026-09-30 | bitget | 2 | 0 | 31 | 1 | 0 | 0 | 0 | 0 |
| 2026-09-30 | solana | 6 | 0 | 37 | 57 | 2 | 0 | 0 | 0 |
| 2026-10-01 | bitget | 4 | 0 | 64 | 0 | 0 | 0 | 0 | 0 |
| 2026-10-01 | solana | 4 | 0 | 30 | 34 | 0 | 0 | 0 | 0 |
| 2026-10-02 | bitget | 4 | 1 | 64 | 0 | 0 | 0 | 0 | 0 |
| 2026-10-02 | solana | 4 | 1 | 28 | 35 | 1 | 0 | 0 | 0 |
| 2026-10-03 | bitget | 5 | 5 | 60 | 6 | 14 | 0 | 0 | 0 |
| 2026-10-03 | solana | 5 | 5 | 38 | 40 | 2 | 0 | 0 | 0 |
| 2026-10-04 | bitget | 5 | 5 | 62 | 7 | 11 | 0 | 0 | 0 |
| 2026-10-04 | solana | 5 | 5 | 42 | 38 | 0 | 0 | 0 | 0 |
| 2026-10-05 | bitget | 4 | 2 | 64 | 0 | 0 | 0 | 0 | 0 |
| 2026-10-05 | solana | 4 | 2 | 30 | 34 | 0 | 0 | 0 | 0 |
| 2026-10-06 | bitget | 4 | 0 | 64 | 0 | 0 | 0 | 0 | 0 |
| 2026-10-06 | solana | 4 | 0 | 35 | 28 | 1 | 0 | 0 | 0 |
| 2026-10-07 | bitget | 4 | 0 | 64 | 0 | 0 | 0 | 0 | 0 |
| 2026-10-07 | solana | 4 | 0 | 39 | 24 | 1 | 0 | 0 | 0 |
| 2026-10-08 | bitget | 4 | 0 | 64 | 0 | 0 | 0 | 0 | 0 |
| 2026-10-08 | solana | 4 | 0 | 32 | 32 | 0 | 0 | 0 | 0 |
| 2026-10-09 | bitget | 4 | 1 | 64 | 0 | 0 | 0 | 0 | 0 |
| 2026-10-09 | solana | 4 | 1 | 35 | 27 | 2 | 0 | 0 | 0 |
| 2026-10-10 | bitget | 4 | 4 | 43 | 10 | 11 | 0 | 0 | 0 |
| 2026-10-10 | solana | 4 | 4 | 37 | 25 | 2 | 0 | 0 | 0 |
| 2026-10-11 | bitget | 1 | 1 | 9 | 3 | 4 | 0 | 0 | 0 |
| 2026-10-11 | solana | 1 | 1 | 10 | 6 | 0 | 0 | 0 | 0 |
