"""Record one live sweep of every ticker to the public run log.

    python scripts/record_run.py

Appends one line per sweep to runs/YYYY-MM-DD.jsonl (UTC date) and rewrites
runs/README.md, a per-day tally of verdicts. A scheduled GitHub Action runs this
every hour and commits the result, so each record carries a timestamp the
repository history vouches for.
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from oracle.service import VERDICTS_ORDER, sweep_json  # noqa: E402

RUNS = ROOT / "runs"


def main() -> None:
    sweep = json.loads(sweep_json())
    RUNS.mkdir(exist_ok=True)
    day = time.strftime("%Y-%m-%d", time.gmtime(sweep["at"] / 1000))
    with (RUNS / f"{day}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(sweep) + "\n")
    write_summary()
    tally = Counter(q.get("verdict") or "ERROR" for q in sweep["quotes"])
    print(day, dict(tally))


def write_summary() -> None:
    rows = []
    for path in sorted(RUNS.glob("*.jsonl")):
        sweeps = [json.loads(line) for line in path.read_text().splitlines() if line]
        tally = Counter(q.get("verdict") or "ERROR"
                        for s in sweeps for q in s["quotes"])
        gap = sum(1 for s in sweeps if any(q.get("weekend_gap") for q in s["quotes"]))
        rows.append((path.stem, len(sweeps), gap, tally))
    cols = list(VERDICTS_ORDER) + ["ERROR"]
    lines = [
        "# Run log",
        "",
        "Every hour a scheduled GitHub Action quotes every ticker in the panel",
        "through the same code the live site runs (`scripts/record_run.py`) and",
        "commits the full response here, one JSON line per sweep, in",
        "`runs/YYYY-MM-DD.jsonl` (UTC). The commit history is the timestamp.",
        "",
        "Counts are ticker-quotes per verdict for each UTC day. *Weekend sweeps*",
        "are those taken while the US cash market was closed for the weekend.",
        "",
        "| Day (UTC) | Sweeps | Weekend sweeps | " + " | ".join(cols) + " |",
        "|---|---|---|" + "---|" * len(cols),
    ]
    for day, n, gap, tally in rows:
        lines.append(f"| {day} | {n} | {gap} | " +
                     " | ".join(str(tally.get(c, 0)) for c in cols) + " |")
    (RUNS / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
