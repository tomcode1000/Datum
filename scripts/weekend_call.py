"""The weekend call: an out-of-sample test, pre-registered and scored in public.

    python scripts/weekend_call.py call     # at the Friday close (Fri 16:05 ET)
    python scripts/weekend_call.py score    # after the Monday open (Mon 10:35 ET)

The three predictions below are fixed in code and committed before the weekend
they are tested on. `call` snapshots both venues at the Friday close into
calls/<friday>/call.json. The hourly run log (scripts/record_run.py) records the
weekend. `score` takes a fresh snapshot one hour after the Monday open, scores
every prediction on both venues from those records, and writes RESULT.md,
whichever way it comes out. A GitHub Action runs both on schedule, so the
commit history timestamps the call before the outcome exists.
"""
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from oracle.service import VENUES, sweep_json  # noqa: E402

CALLS = ROOT / "calls"
RUNS = ROOT / "runs"

PREDICTIONS = [
    ("drift", "Over the weekend the tokens drift: on each venue, the median "
              "|deviation| across all weekend ticker-hours is larger than the "
              "median |deviation| at the Friday close."),
    ("convergence", "After the Monday open they come back: on each venue, the "
                    "median |deviation| one hour after the open is smaller than "
                    "the weekend median."),
    ("pullback", "Tokens outside their band just before the open are pulled "
                 "toward the reference: on each venue, at least half of them "
                 "are closer to it one hour after the open."),
]


def snapshot() -> dict:
    """Both venues' live sweep, reduced to what the call is scored on."""
    out = {}
    for venue in VENUES:
        s = json.loads(sweep_json(venue))
        out[venue] = {q["ticker"]: {k: q.get(k) for k in
                                    ("verdict", "deviation_bps", "expected_bps",
                                     "reference", "pool", "session")}
                      for q in s["quotes"] if "ticker" in q}
    return {"at": int(time.time() * 1000), "venues": out}


def _abs_devs(rows) -> list[float]:
    return [abs(r["deviation_bps"]) for r in rows if r.get("deviation_bps") is not None]


def _median(xs):
    return round(statistics.median(xs), 1) if xs else None


def _bps(x) -> str:
    return "N/A" if x is None else f"{x} bps"


def call() -> Path:
    snap = snapshot()
    day = time.strftime("%Y-%m-%d", time.gmtime(snap["at"] / 1000))
    d = CALLS / day
    d.mkdir(parents=True, exist_ok=True)
    body = {"made_at": snap["at"], "predictions": dict(PREDICTIONS), "friday_close": snap}
    (d / "call.json").write_text(json.dumps(body, indent=1), encoding="utf-8")
    lines = [f"# Weekend call, made {time.strftime('%a %d %b %Y %H:%M UTC', time.gmtime(snap['at'] / 1000))}",
             "", "Committed at the Friday close, before the weekend it predicts. Scored after the",
             "Monday open by `scripts/weekend_call.py score`, whichever way it comes out.", "",
             "## Predictions", ""]
    lines += [f"{i}. **{k}**: {text}" for i, (k, text) in enumerate(PREDICTIONS, 1)]
    lines += ["", "## Friday close", "", "| Venue | Tickers quoted | Median abs deviation | Outside band |",
              "|---|---|---|---|"]
    for venue, rows in snap["venues"].items():
        out_band = sum(1 for r in rows.values() if r.get("deviation_bps") is not None
                       and r.get("expected_bps") and abs(r["deviation_bps"]) > r["expected_bps"])
        lines.append(f"| {venue} | {len(rows)} | {_bps(_median(_abs_devs(rows.values())))} | {out_band} |")
    (d / "CALL.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("call written:", d)
    return d


def _weekend_sweeps(since_ms: int, until_ms: int):
    """Hourly run-log sweeps taken in the weekend gap between two instants."""
    for path in sorted(RUNS.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            s = json.loads(line)
            if not (since_ms < s["at"] < until_ms):
                continue
            if any(q.get("weekend_gap") for q in s["quotes"]):
                yield s.get("venue", "solana"), s


def score() -> Path:
    pending = [p for p in sorted(CALLS.glob("*/call.json")) if not (p.parent / "result.json").exists()]
    if not pending:
        print("no open call to score")
        sys.exit(0)
    path = pending[-1]
    c = json.loads(path.read_text(encoding="utf-8"))
    monday = snapshot()
    weekend = {v: [] for v in VENUES}
    last_before_open = {}
    for venue, s in _weekend_sweeps(c["made_at"], monday["at"]):
        weekend[venue].extend(q for q in s["quotes"] if q.get("deviation_bps") is not None)
        last_before_open[venue] = {q["ticker"]: q for q in s["quotes"]}
    results = {}
    for venue in VENUES:
        fri = _median(_abs_devs(c["friday_close"]["venues"].get(venue, {}).values()))
        wk = _median(_abs_devs(weekend[venue]))
        mon = _median(_abs_devs(monday["venues"][venue].values()))
        outside = [t for t, q in last_before_open.get(venue, {}).items()
                   if q.get("deviation_bps") is not None and q.get("expected_bps")
                   and abs(q["deviation_bps"]) > q["expected_bps"]]
        closer = [t for t in outside
                  if monday["venues"][venue].get(t, {}).get("deviation_bps") is not None
                  and abs(monday["venues"][venue][t]["deviation_bps"])
                  < abs(last_before_open[venue][t]["deviation_bps"])]
        results[venue] = {
            "friday_close_median_bps": fri, "weekend_median_bps": wk,
            "monday_median_bps": mon, "weekend_ticker_hours": len(weekend[venue]),
            "outside_band_before_open": outside, "closer_after_open": closer,
            "drift": None if fri is None or wk is None else wk > fri,
            "convergence": None if wk is None or mon is None else mon < wk,
            "pullback": None if not outside else len(closer) * 2 >= len(outside),
        }
    (path.parent / "result.json").write_text(json.dumps(
        {"scored_at": monday["at"], "monday": monday, "results": results}, indent=1), encoding="utf-8")
    mark = {True: "held", False: "failed", None: "not testable"}
    lines = [f"# Weekend call, scored {time.strftime('%a %d %b %Y %H:%M UTC', time.gmtime(monday['at'] / 1000))}",
             "", "Predictions as committed in `CALL.md`, scored against the hourly run log.", "",
             "| Venue | Friday close | Weekend | Monday +1h | Drift | Convergence | Pull-back |",
             "|---|---|---|---|---|---|---|"]
    for venue, r in results.items():
        pb = (f"{len(r['closer_after_open'])} of {len(r['outside_band_before_open'])}"
              if r["outside_band_before_open"] else "none outside")
        lines.append(f"| {venue} | {_bps(r['friday_close_median_bps'])} | {_bps(r['weekend_median_bps'])} "
                     f"({r['weekend_ticker_hours']} ticker-hours) | {_bps(r['monday_median_bps'])} | "
                     f"{mark[r['drift']]} | {mark[r['convergence']]} | {mark[r['pullback']]} ({pb}) |")
    lines += ["", "Medians are of absolute deviation from the Hyperliquid reference, in bps."]
    (path.parent / "RESULT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("scored:", path.parent)
    return path.parent


if __name__ == "__main__":
    {"call": call, "score": score}[sys.argv[1] if len(sys.argv) > 1 else "call"]()
