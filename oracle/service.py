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
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from .calendar import in_weekend_gap
from .dataset import HOUR_MS
from .model import LiquidityModel
from .sources import (ACTIVITY_WINDOWS, hl_context, pool_last_trade_ms,
                      xstock_mint, xstock_pool, xstock_pools_live)

ROOT = Path(__file__).resolve().parent.parent
PANEL = ROOT / "panel.json"
# Ticker -> genuine mint and deepest pool, from scripts/resolve_pools.py. They
# do not move, and resolving them live costs two rate-limited calls per ticker.
POOLS = ROOT / "pools.json"
_POOL_MAP = json.loads(POOLS.read_text()) if POOLS.exists() else {}

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


def _median_volume(ticker: str) -> float | None:
    """The measured median weekend volume the model was fitted on."""
    for row in json.loads(PANEL.read_text())["tickers"]:
        if row["ticker"] == ticker:
            return row.get("median_weekend_volume")
    return None


def _pool_address(ticker: str) -> str | None:
    pool = _POOL_MAP.get(ticker, {}).get("pool")
    if pool:
        return pool
    found = xstock_mint(ticker)
    return xstock_pool(found[0]) if found else None


def _stale_hours(pool: str, attrs: dict) -> float:
    """Hours since the pool last traded.

    An active pool is placed in the shortest activity window that holds a
    trade (5, 15, 30 or 60 minutes), so the figure is an upper bound. A pool
    quiet for over an hour costs one more call for its exact last trade, since
    that is the case the STALE verdict turns on; if that call fails, the
    windows' lower bound is used instead."""
    tx = attrs.get("transactions") or {}
    for key, hours in ACTIVITY_WINDOWS:
        w = tx.get(key) or {}
        if (w.get("buys") or 0) + (w.get("sells") or 0) > 0:
            return hours
    try:
        last = pool_last_trade_ms(pool)
    except Exception:
        # The windows still bound it from below: no trade inside an hour, and
        # none inside six or 24 when those are empty too.
        h6 = tx.get("h6") or {}
        h24 = tx.get("h24") or {}
        if (h6.get("buys") or 0) + (h6.get("sells") or 0) > 0:
            return 1.05         # past the hour window, so never read as "within 1h"
        if (h24.get("buys") or 0) + (h24.get("sells") or 0) > 0:
            return 6.0
        return 24.0
    if last is None:
        return 24.0             # nothing in the 24h the trades feed covers
    return (time.time() * 1000 - last) / HOUR_MS


def _pool_state(ticker: str, live: dict[str, dict] | None = None
                ) -> tuple[float | None, float | None, float | None]:
    """(current pool price, median weekend volume, hours since a real trade)."""
    pool = _pool_address(ticker)
    if not pool:
        return None, None, None
    attrs = (live if live is not None else xstock_pools_live([pool])).get(pool)
    if not attrs or attrs.get("base_token_price_usd") is None:
        return None, None, None
    price = float(attrs["base_token_price_usd"])
    return price, _median_volume(ticker), _stale_hours(pool, attrs)


def quote(ticker: str, contexts: dict[str, dict] | None = None,
          live: dict[str, dict] | None = None) -> Quote:
    contexts = contexts if contexts is not None else hl_context()
    ticker = ticker.upper()
    # Accept the token symbol ("TSLAx") as well as the ticker, but only strip
    # the x when the full name is not itself a market: SPCX is a ticker.
    if ticker not in contexts and ticker.endswith("X") and ticker[:-1] in contexts:
        ticker = ticker[:-1]
    gap = in_weekend_gap(int(time.time() * 1000))

    ctx = contexts.get(ticker)
    if not ctx:
        return Quote(ticker, NO_REFERENCE, gap, None, None, None, None, None,
                     None, None,
                     "No 24/7 reference market for this ticker.")
    reference = float(ctx["markPx"])

    price, median_vol, stale_hours = _pool_state(ticker, live)
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
        since = ("at least 24h" if stale_hours >= 24 else f"{stale_hours:.1f}h")
        advice = (f"Pool has not traded for {since}. Treat the "
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
    """Quote every ticker from one reference call and one pool call, plus one
    trades call per pool that has been quiet for over an hour. A ticker that
    fails is reported as an error, never as a verdict."""
    contexts = hl_context()
    pools = [p for p in (_pool_address(t) for t in tickers) if p]
    live = xstock_pools_live(pools)
    out: list[Quote | dict] = []
    for t in tickers:
        try:
            out.append(quote(t, contexts, live))
        except Exception as exc:
            out.append({"ticker": t, "error": f"{type(exc).__name__}: {exc}"})
    return out


# One sweep serves every caller for five minutes: the local server and the
# hosted function both answer /api/quotes from here, and the hosted one also
# tells the CDN to hold the response for the same window.
SWEEP_TTL = 300
_sweep: dict = {"at": 0.0, "body": None}
_sweep_lock = threading.Lock()


def sweep_json() -> str:
    with _sweep_lock:
        if _sweep["body"] and time.time() - _sweep["at"] < SWEEP_TTL:
            return _sweep["body"]
        tickers = [t["ticker"] for t in json.loads(PANEL.read_text())["tickers"]]
        out = [q if isinstance(q, dict) else asdict(q) for q in quote_all(tickers)]
        now = time.time()
        _sweep.update(at=now, body=json.dumps(
            {"at": int(now * 1000), "every_s": SWEEP_TTL, "quotes": out}))
        return _sweep["body"]
