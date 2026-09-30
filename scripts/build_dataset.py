"""Build the full weekend panel and fit both models.

    python scripts/build_dataset.py              # Solana xStocks -> panel.json
    python scripts/build_dataset.py bitget       # Bitget rTokens -> panel-bitget.json

Writes panel.json (per-ticker summary + fitted model) and prints the table that
backs the submission's headline numbers. Responses are cached under cache/, so
a second run is near-instant.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle.dataset import HORIZONS, build_pair               # noqa: E402
from oracle.model import LiquidityModel, convergence, pearson  # noqa: E402
from oracle.sources import (hl_universe, rtoken_symbol,        # noqa: E402
                            rtoken_tickers_live)

ROOT = Path(__file__).resolve().parent.parent


def panel_path(venue: str) -> Path:
    return ROOT / ("panel.json" if venue == "solana" else f"panel-{venue}.json")


def main() -> None:
    venue = sys.argv[1] if len(sys.argv) > 1 else "solana"
    out_path = panel_path(venue)
    tickers = hl_universe()
    if venue == "bitget":
        # only tickers Bitget lists as an rToken
        listed = set(rtoken_tickers_live())
        tickers = [t for t in tickers if rtoken_symbol(t) in listed]
    print(f"builder-dex tickers: {len(tickers)}", flush=True)
    print(f"{'ticker':9}{'n':>6}"
          + "".join(f"{str(h) + 'h':>9}" for h in HORIZONS)
          + f"{'|dev|bps':>10}{'liq$':>12}{'vol$/hr':>10}", flush=True)

    pairs, rows = [], []
    for t in tickers:
        try:
            pair = build_pair(t, venue=venue)
        except Exception as exc:          # a dead pool must not stop the run
            print(f"{t:9}  skipped ({type(exc).__name__})", flush=True)
            continue
        if not pair:
            continue
        conv = convergence(pair)

        def fmt(v):
            return f"{v:>+9.3f}" if v is not None else f"{'-':>9}"

        print(f"{pair.ticker:9}{len(pair.obs):>6}"
              + "".join(fmt(conv[h]) for h in HORIZONS)
              + f"{pair.mean_abs_deviation * 1e4:>10.1f}"
              + f"{pair.liquidity:>12,.0f}{pair.median_volume:>10,.0f}",
              flush=True)
        pairs.append(pair)
        rows.append(dict(ticker=pair.ticker, n=len(pair.obs),
                         convergence={str(h): conv[h] for h in HORIZONS},
                         mean_abs_dev_bps=pair.mean_abs_deviation * 1e4,
                         liquidity=pair.liquidity,
                         median_weekend_volume=pair.median_volume))

    if not pairs:
        print("\nno usable pairs")
        return

    model = LiquidityModel.fit(pairs)
    one_hour = [c for c in (convergence(p)[1] for p in pairs) if c is not None]
    # The convergence claim uses every ticker -- that it holds universally is
    # the point. The cross-sectional fit uses only tickers with enough weekend
    # observations to be stable, so each is reported against its own n.
    fitted = [p for p in pairs if p.median_volume > 0 and p.reliable]
    logv = [math.log(p.median_volume) for p in fitted]
    devs = [p.mean_abs_deviation for p in fitted]
    liqs = [math.log(p.liquidity) for p in fitted if p.liquidity > 0]
    thin = sorted(p.ticker for p in pairs if not p.reliable)

    print(f"\nCONVERGENCE  (all {len(pairs)} tickers)")
    print(f"  all 1h slopes negative: {all(c < 0 for c in one_hour)}")
    print(f"  mean 1h slope {sum(one_hour) / len(one_hour):+.3f}  "
          f"range {min(one_hour):+.3f} to {max(one_hour):+.3f}")
    print(f"\nCROSS-SECTION  ({len(fitted)} tickers; excluded for thin "
          f"weekend samples: {', '.join(thin) or 'none'})")
    print(f"  corr(log weekend volume, |dev|)  = {pearson(logv, devs):+.3f}")
    if len(liqs) == len(devs):
        print(f"  corr(log pool liquidity, |dev|)  = {pearson(liqs, devs):+.3f}")
        print("  (neither measure is sharper; do not claim volume beats TVL)")
    print(f"\nmodel: |dev| bps = {model.a * 1e4:.1f} {model.b * 1e4:+.1f}"
          f" * ln(weekend hourly volume)   R2 = {model.r2:.2f}")
    for v in (100, 1_000, 10_000):
        print(f"   ${v:>7,}/hr -> {model.deviation_bps(v):>5.0f} bps")

    out_path.write_text(json.dumps(dict(
        tickers=rows,
        model=dict(a=model.a, b=model.b, r2=model.r2,
                   volume_lo=model.lo, volume_hi=model.hi),
    ), indent=2))
    print(f"\nwrote {out_path.name} ({len(rows)} tickers)")


if __name__ == "__main__":
    main()
