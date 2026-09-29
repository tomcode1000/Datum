"""The oracle itself: what a consumer of this project actually calls.

For a tokenized stock it answers three questions a lending protocol, NAV
process or liquidation engine has to answer during the weekend gap:

  1. What is this actually worth right now?        -> reference price
  2. How wrong is the on-chain quote likely to be? -> expected deviation band
  3. Can I trust the on-chain quote at all?        -> staleness + verdict

The reference is the Hyperliquid 24/7 equity perp. That choice is empirical,
not aesthetic: weekend drift on the perp is retained through the following
Monday US open (retention ~1.05, r ~0.86 across 21 weekends), so it behaves as
genuine price discovery rather than something to be arbitraged.
"""
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from .calendar import in_weekend_gap
from .dataset import HOUR_MS
from .model import LiquidityModel
from .sources import hl_context, xstock_candles, xstock_mint, xstock_pool

PANEL = Path(__file__).resolve().parent.parent / "panel.json"

# Beyond this the pool price is not a lagging price, it is an absent one. The
# thinnest markets we measured (AVGO at ~$32/hr) go many hours between trades.
STALE_AFTER_HOURS = 3.0

OK = "OK"                  # quote sits inside the expected band
LAGGED = "LAGGED"          # quote is outside the band; expect convergence
STALE = "STALE"            # pool has not traded recently; quote is not a price
NO_REFERENCE = "NO_REFERENCE"
NO_POOL = "NO_POOL"


@dataclass
class Quote:
    ticker: str
    verdict: str
    weekend_gap: bool
    reference: float | None          # fair value, USD
    pool: float | None               # on-chain quote, USD
    deviation_bps: float | None      # pool vs reference
    expected_bps: float | None       # typical |deviation| for this liquidity
    band_low: float | None
    band_high: float | None
    stale_hours: float | None
    advice: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def _model() -> LiquidityModel:
    if not PANEL.exists():
        raise FileNotFoundError(
            "panel.json missing - run scripts/build_dataset.py first")
    m = json.loads(PANEL.read_text())["model"]
    return LiquidityModel(m["a"], m["b"], m["r2"], m["volume_lo"], m["volume_hi"])


def _pool_state(ticker: str) -> tuple[float | None, float | None, float | None]:
    """(latest pool price, median weekend volume, hours since a real trade)."""
    found = xstock_mint(ticker)
    if not found:
        return None, None, None
    pool = xstock_pool(found[0])
    if not pool:
        return None, None, None
    bars = xstock_candles(pool, pages=1)
    if not bars:
        return None, None, None

    latest_ts = max(bars)
    price = bars[latest_ts][0]
    traded = [ts for ts, (_p, vol) in bars.items() if vol > 0]
    stale_hours = ((time.time() * 1000 - max(traded)) / HOUR_MS
                   if traded else None)
    weekend_vols = sorted(v for ts, (_p, v) in bars.items()
                          if in_weekend_gap(ts) and v > 0)
    median = (weekend_vols[len(weekend_vols) // 2] if weekend_vols else None)
    return price, median, stale_hours


def quote(ticker: str) -> Quote:
    ticker = ticker.upper().removesuffix("X")
    gap = in_weekend_gap(int(time.time() * 1000))

    ctx = hl_context().get(ticker)
    if not ctx:
        return Quote(ticker, NO_REFERENCE, gap, None, None, None, None, None,
                     None, None,
                     "No 24/7 reference market for this ticker.")
    reference = float(ctx["markPx"])

    price, median_vol, stale_hours = _pool_state(ticker)
    if price is None:
        return Quote(ticker, NO_POOL, gap, reference, None, None, None, None,
                     None, None,
                     "No genuine xStocks pool found; reference price only.")

    model = _model()
    expected = model.deviation_bps(median_vol or model.lo)
    half = reference * expected / 10_000
    deviation = (price / reference - 1) * 10_000

    if stale_hours is not None and stale_hours > STALE_AFTER_HOURS:
        verdict = STALE
        advice = (f"Pool has not traded for {stale_hours:.1f}h. Treat the "
                  f"on-chain quote as absent and price from the reference.")
    elif abs(deviation) > expected:
        verdict = LAGGED
        advice = (f"Quote is {deviation:+.0f}bps vs reference, outside the "
                  f"+/-{expected:.0f}bps typical for this liquidity. Expect "
                  f"convergence over 1-12h; price from the reference instead.")
    else:
        verdict = OK
        advice = (f"Quote is {deviation:+.0f}bps vs reference, within the "
                  f"+/-{expected:.0f}bps typical for this liquidity.")

    if not gap:
        advice += " US cash market is open; the pool has a live anchor."

    return Quote(ticker, verdict, gap, reference, price, deviation, expected,
                 reference - half, reference + half, stale_hours, advice)


def quote_all(tickers: list[str]) -> list[Quote | dict]:
    """Quote every ticker, one at a time. GeckoTerminal allows 30 requests a
    minute and each quote costs an uncached candle request (followed by the
    4s pause in xstock_candles), so running these in parallel draws 429s. A
    ticker that fails is reported as an error, never as a verdict."""
    out: list[Quote | dict] = []
    for t in tickers:
        try:
            out.append(quote(t))
        except Exception as exc:
            out.append({"ticker": t, "error": f"{type(exc).__name__}: {exc}"})
    return out
