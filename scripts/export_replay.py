"""Export weekend replays for the UI.

The demo has to be compelling on a Tuesday afternoon, not only at the weekend,
so the primary surface replays historical weekends rather than showing live
state. This dumps every weekend window we have, per ticker, as a small JSON the
page loads directly.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle.calendar import to_ny, weekend_windows              # noqa: E402
from oracle.dataset import HOUR_MS, build_pair                   # noqa: E402
from oracle.model import LiquidityModel, convergence             # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MIN_POINTS = 12   # a weekend with fewer bars than this is not worth plotting


def main() -> None:
    venue = sys.argv[1] if len(sys.argv) > 1 else "solana"
    suffix = "" if venue == "solana" else f"-{venue}"
    OUT = ROOT / "ui" / f"replay{suffix}.json"
    panel = json.loads((ROOT / f"panel{suffix}.json").read_text())
    m = panel["model"]
    model = LiquidityModel(m["a"], m["b"], m["r2"], m["volume_lo"], m["volume_hi"])
    tickers = [r["ticker"] for r in panel["tickers"] if r["n"] >= 200]
    if venue != "solana":
        # The page compares venues like for like, so another venue shows the
        # tickers Solana measured. Its fit still uses its whole panel.
        shared = {r["ticker"] for r in json.loads((ROOT / "panel.json").read_text())["tickers"]}
        tickers = [t for t in tickers if t in shared]

    out = {"venue": venue, "model": m, "tickers": {}}
    for ticker in tickers:
        pair = build_pair(ticker, venue=venue)
        if not pair:
            continue
        by_ts = {o.ts: o for o in pair.obs}
        expected = model.deviation_bps(pair.median_volume or model.lo)
        weekends = []
        lo, hi = min(by_ts), max(by_ts)
        for close_ms, open_ms in weekend_windows(lo - 3 * 86_400_000, hi + HOUR_MS):
            pts = [o for ts, o in sorted(by_ts.items())
                   if close_ms <= ts <= open_ms]
            if len(pts) < MIN_POINTS:
                continue
            weekends.append({
                "label": to_ny(close_ms).strftime("%d %b %Y"),
                "close_ms": close_ms,
                "open_ms": open_ms,
                "series": [{"t": o.ts,
                            "ref": round(o.reference, 4),
                            "pool": round(o.pool, 4),
                            "dev": round(o.deviation * 1e4, 1)}
                           for o in pts],
            })
        if not weekends:
            continue
        conv = convergence(pair)
        out["tickers"][ticker] = {
            "expected_bps": round(expected, 1),
            "median_weekend_volume": pair.median_volume,
            "liquidity": pair.liquidity,
            "mean_abs_dev_bps": round(pair.mean_abs_deviation * 1e4, 1),
            "convergence_1h": conv[1],
            "weekends": weekends,
        }
        print(f"{ticker:8} {len(weekends):>3} weekends  "
              f"+/-{expected:.0f}bps expected", flush=True)

    OUT.write_text(json.dumps(out, separators=(",", ":")))
    size = OUT.stat().st_size / 1024
    print(f"\nwrote ui/{OUT.name}  {size:.0f} KB  "
          f"{len(out['tickers'])} tickers")


if __name__ == "__main__":
    main()
