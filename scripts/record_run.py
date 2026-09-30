"""Record one live sweep of every ticker, on both venues, to the public run log.

    python scripts/record_run.py

Appends one line per venue per sweep to runs/YYYY-MM-DD.jsonl (UTC date) and
rewrites runs/README.md, a per-day tally of verdicts. A scheduled GitHub Action
runs this every hour and commits the result, so each record carries a timestamp
the repository history vouches for. The weekend call (scripts/weekend_call.py)
is scored from these records.
"""
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from oracle.service import VENUES, VERDICTS_ORDER, sweep_json  # noqa: E402

RUNS = ROOT / "runs"


def main() -> None:
    RUNS.mkdir(exist_ok=True)
    for venue in VENUES:
        try:
            sweep = json.loads(sweep_json(venue))
        except Exception as exc:          # one venue failing must not lose the other
            print(venue, "failed:", type(exc).__name__, exc)
            continue
        sweep.setdefault("venue", venue)
        day = time.strftime("%Y-%m-%d", time.gmtime(sweep["at"] / 1000))
        with (RUNS / f"{day}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(sweep) + "\n")
        tally = Counter(q.get("verdict") or "ERROR" for q in sweep["quotes"])
        print(day, venue, dict(tally))
    write_summary()


def load_sweeps():
    for path in sorted(RUNS.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                s = json.loads(line)
                s.setdefault("venue", "solana")   # the first days logged Solana only
                yield path.stem, s


def write_summary() -> None:
    rows = defaultdict(lambda: {"n": 0, "gap": 0, "tally": Counter()})
    for day, s in load_sweeps():
        r = rows[(day, s["venue"])]
        r["n"] += 1
        r["gap"] += any(q.get("weekend_gap") for q in s["quotes"])
        r["tally"].update(q.get("verdict") or "ERROR" for q in s["quotes"])
    cols = list(VERDICTS_ORDER) + ["ERROR"]
    lines = [
        "# Run log",
        "",
        "Every hour a scheduled GitHub Action quotes every ticker on both venues",
        "through the same code the live site runs (`scripts/record_run.py`) and",
        "commits the full response here, one JSON line per venue per sweep, in",
        "`runs/YYYY-MM-DD.jsonl` (UTC). The commit history is the timestamp.",
        "",
        "Counts are ticker-quotes per verdict for each UTC day and venue. *Weekend",
        "sweeps* were taken while the US cash market was closed for the weekend.",
        "",
        "| Day (UTC) | Venue | Sweeps | Weekend sweeps | " + " | ".join(cols) + " |",
        "|---|---|---|---|" + "---|" * len(cols),
    ]
    for (day, venue), r in sorted(rows.items()):
        lines.append(f"| {day} | {venue} | {r['n']} | {r['gap']} | " +
                     " | ".join(str(r["tally"].get(c, 0)) for c in cols) + " |")
    (RUNS / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
