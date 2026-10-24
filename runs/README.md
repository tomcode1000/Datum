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
| 2026-10-11 | bitget | 5 | 5 | 55 | 11 | 14 | 0 | 0 | 0 |
| 2026-10-11 | solana | 5 | 5 | 44 | 34 | 2 | 0 | 0 | 0 |
| 2026-10-12 | bitget | 3 | 2 | 47 | 1 | 0 | 0 | 0 | 0 |
| 2026-10-12 | solana | 3 | 2 | 25 | 21 | 2 | 0 | 0 | 0 |
| 2026-10-13 | bitget | 4 | 0 | 63 | 1 | 0 | 0 | 0 | 0 |
| 2026-10-13 | solana | 4 | 0 | 34 | 30 | 0 | 0 | 0 | 0 |
| 2026-10-14 | bitget | 5 | 0 | 80 | 0 | 0 | 0 | 0 | 0 |
| 2026-10-14 | solana | 5 | 0 | 48 | 32 | 0 | 0 | 0 | 0 |
| 2026-10-15 | bitget | 5 | 0 | 80 | 0 | 0 | 0 | 0 | 0 |
| 2026-10-15 | solana | 5 | 0 | 48 | 32 | 0 | 0 | 0 | 0 |
| 2026-10-16 | bitget | 6 | 2 | 92 | 4 | 0 | 0 | 0 | 0 |
| 2026-10-16 | solana | 6 | 2 | 59 | 35 | 2 | 0 | 0 | 0 |
| 2026-10-17 | bitget | 6 | 6 | 0 | 0 | 96 | 0 | 0 | 0 |
| 2026-10-17 | solana | 6 | 6 | 40 | 52 | 4 | 0 | 0 | 0 |
| 2026-10-18 | bitget | 7 | 7 | 0 | 0 | 112 | 0 | 0 | 0 |
| 2026-10-18 | solana | 7 | 7 | 63 | 46 | 3 | 0 | 0 | 0 |
| 2026-10-19 | bitget | 4 | 2 | 64 | 0 | 0 | 0 | 0 | 0 |
| 2026-10-19 | solana | 4 | 2 | 32 | 32 | 0 | 0 | 0 | 0 |
| 2026-10-20 | bitget | 6 | 0 | 95 | 1 | 0 | 0 | 0 | 0 |
| 2026-10-20 | solana | 6 | 0 | 53 | 42 | 1 | 0 | 0 | 0 |
| 2026-10-21 | bitget | 5 | 0 | 77 | 3 | 0 | 0 | 0 | 0 |
| 2026-10-21 | solana | 5 | 0 | 42 | 37 | 1 | 0 | 0 | 0 |
| 2026-10-22 | bitget | 5 | 0 | 76 | 4 | 0 | 0 | 0 | 0 |
| 2026-10-22 | solana | 5 | 0 | 38 | 41 | 1 | 0 | 0 | 0 |
| 2026-10-23 | bitget | 5 | 1 | 78 | 2 | 0 | 0 | 0 | 0 |
| 2026-10-23 | solana | 5 | 1 | 40 | 39 | 1 | 0 | 0 | 0 |
| 2026-10-24 | bitget | 3 | 3 | 34 | 10 | 4 | 0 | 0 | 0 |
| 2026-10-24 | solana | 3 | 3 | 22 | 23 | 3 | 0 | 0 | 0 |
