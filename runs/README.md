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
| 2026-10-01 | bitget | 3 | 0 | 48 | 0 | 0 | 0 | 0 | 0 |
| 2026-10-01 | solana | 3 | 0 | 24 | 24 | 0 | 0 | 0 | 0 |
