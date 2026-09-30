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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from pathlib import Path

from .calendar import in_weekend_gap, session
from .dataset import HOUR_MS
from .model import LiquidityModel
from .sources import (ACTIVITY_WINDOWS, hl_context, pool_last_trade_ms,
                      rtoken_last_trade_ms, rtoken_symbol, rtoken_tickers_live,
                      xstock_mint, xstock_pool, xstock_pools_live)

ROOT = Path(__file__).resolve().parent.parent
PANEL = ROOT / "panel.json"
# Two venues, one reference: Solana xStocks pools and Bitget rTokens. Each has
# its own measured panel and fitted band, so neither borrows the other's fit.
VENUES = ("solana", "bitget")


def panel_path(venue: str = "solana") -> Path:
    return ROOT / ("panel.json" if venue == "solana" else f"panel-{venue}.json")
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
VERDICTS_ORDER = (OK, LAGGED, STALE, NO_POOL, NO_REFERENCE)


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
    venue: str = "solana"
    session: str = ""              # open | overnight | weekend (US cash market)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def _model(venue: str = "solana") -> LiquidityModel:
    path = panel_path(venue)
    if not path.exists():
        raise FileNotFoundError(
            f"{path.name} missing - run scripts/build_dataset.py {venue}")
    m = json.loads(path.read_text())["model"]
    return LiquidityModel(m["a"], m["b"], m["r2"], m["volume_lo"], m["volume_hi"])


def _median_volume(ticker: str, venue: str = "solana") -> float | None:
    """The measured median weekend volume the model was fitted on."""
    for row in json.loads(panel_path(venue).read_text())["tickers"]:
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


def _rtoken_state(ticker: str, live: dict[str, dict] | None = None
                  ) -> tuple[float | None, float | None, float | None]:
    """(last rToken price, median weekend volume, hours since a real trade)."""
    row = (live if live is not None else rtoken_tickers_live()).get(rtoken_symbol(ticker))
    if not row or not row.get("lastPr"):
        return None, None, None
    last = row["_last_ms"] if "_last_ms" in row else rtoken_last_trade_ms(ticker)
    # Candles are keyed by the hour they open, so the trade was at some point
    # in that hour: counting from its end keeps this a lower bound.
    stale = (24.0 if last is None
             else max(0.0, (time.time() * 1000 - last - HOUR_MS) / HOUR_MS))
    return float(row["lastPr"]), _median_volume(ticker, "bitget"), stale


_FAILED = object()


def _safe_last_trade(ticker: str):
    try:
        return rtoken_last_trade_ms(ticker)
    except Exception:
        return _FAILED          # quote() retries it on its own and reports it


def _pool_state(ticker: str, live: dict[str, dict] | None = None,
                venue: str = "solana"
                ) -> tuple[float | None, float | None, float | None]:
    """(current pool price, median weekend volume, hours since a real trade)."""
    if venue == "bitget":
        return _rtoken_state(ticker, live)
    pool = _pool_address(ticker)
    if not pool:
        return None, None, None
    attrs = (live if live is not None else xstock_pools_live([pool])).get(pool)
    if not attrs or attrs.get("base_token_price_usd") is None:
        return None, None, None
    price = float(attrs["base_token_price_usd"])
    return price, _median_volume(ticker), _stale_hours(pool, attrs)


def quote(ticker: str, contexts: dict[str, dict] | None = None,
          live: dict[str, dict] | None = None, venue: str = "solana") -> Quote:
    if venue not in VENUES:
        raise ValueError(f"unknown venue {venue!r}; use one of {', '.join(VENUES)}")
    contexts = contexts if contexts is not None else hl_context()
    ticker = ticker.upper()
    # Accept the token symbol ("TSLAx") as well as the ticker, but only strip
    # the x when the full name is not itself a market: SPCX is a ticker.
    if ticker not in contexts and ticker.endswith("X") and ticker[:-1] in contexts:
        ticker = ticker[:-1]
    # ...and the rToken symbol ("RTSLAUSDT") for the Bitget venue.
    if ticker.startswith("R") and ticker.endswith("USDT") and ticker[1:-4] in contexts:
        ticker = ticker[1:-4]
    now_ms = int(time.time() * 1000)
    gap = in_weekend_gap(now_ms)
    sess = session(now_ms)

    ctx = contexts.get(ticker)
    if not ctx:
        return Quote(ticker, NO_REFERENCE, gap, None, None, None, None, None,
                     None, None,
                     "No 24/7 reference market for this ticker.", venue, sess)
    reference = float(ctx["markPx"])

    price, median_vol, stale_hours = _pool_state(ticker, live, venue)
    if price is None:
        return Quote(ticker, NO_POOL, gap, reference, None, None, None, None,
                     None, None,
                     ("No Bitget rToken listed for this ticker"
                      if venue == "bitget" else "No genuine xStocks pool found")
                     + "; reference price only.", venue, sess)

    model = _model(venue)
    expected = model.deviation_bps(median_vol or model.lo)
    half = reference * expected / 10_000
    deviation = (price / reference - 1) * 10_000

    if stale_hours is not None and stale_hours > STALE_AFTER_HOURS:
        verdict = STALE
        since = ("at least 24h" if stale_hours >= 24 else f"{stale_hours:.1f}h")
        advice = (f"{'The rToken' if venue == 'bitget' else 'Pool'} has not "
                  f"traded for {since}. Treat the "
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

    # Only in the cash session does the quote have a live anchor; saying so on
    # any weekday (as this once did) was false every weeknight.
    if sess == "open":
        advice += " US cash market is open; the quote has a live anchor."

    return Quote(ticker, verdict, gap, reference, price, deviation, expected,
                 reference - half, reference + half, stale_hours, advice, venue,
                 sess)


def quote_all(tickers: list[str], venue: str = "solana") -> list[Quote | dict]:
    """Quote every ticker from one reference call and one venue call, plus
    one small call per ticker for its last trade where that needs checking. A
    ticker that fails is reported as an error, never as a verdict."""
    contexts = hl_context()
    if venue == "bitget":
        live = rtoken_tickers_live()
        with ThreadPoolExecutor(max_workers=8) as pool:
            lasts = dict(zip(tickers, pool.map(_safe_last_trade, tickers)))
        for t, last in lasts.items():
            row = live.get(rtoken_symbol(t))
            if row is not None and last is not _FAILED:
                row["_last_ms"] = last
    else:
        pools = [p for p in (_pool_address(t) for t in tickers) if p]
        live = xstock_pools_live(pools)
    out: list[Quote | dict] = []
    for t in tickers:
        try:
            out.append(quote(t, contexts, live, venue))
        except Exception as exc:
            out.append({"ticker": t, "venue": venue,
                        "error": f"{type(exc).__name__}: {exc}"})
    return out


# One sweep per venue serves every caller for five minutes: the local server
# and the hosted function both answer /api/quotes from here, and the hosted one
# also tells the CDN to hold the response for the same window.
SWEEP_TTL = 300
_sweeps: dict[str, dict] = {}
_sweep_lock = threading.Lock()


def sweep_tickers(venue: str = "solana") -> list[str]:
    """The tickers a live sweep covers: Solana's panel, and on another venue
    the same tickers where that venue measured them, so the two compare."""
    solana = [t["ticker"] for t in json.loads(PANEL.read_text())["tickers"]]
    if venue == "solana":
        return solana
    measured = {t["ticker"] for t in json.loads(panel_path(venue).read_text())["tickers"]}
    return [t for t in solana if t in measured]


def sweep_json(venue: str = "solana") -> str:
    if venue not in VENUES:
        raise ValueError(f"unknown venue {venue!r}; use one of {', '.join(VENUES)}")
    with _sweep_lock:
        hit = _sweeps.get(venue)
        if hit and time.time() - hit["at"] < SWEEP_TTL:
            return hit["body"]
        out = [q if isinstance(q, dict) else asdict(q)
               for q in quote_all(sweep_tickers(venue), venue)]
        now = time.time()
        body = json.dumps({"at": int(now * 1000), "venue": venue,
                           "every_s": SWEEP_TTL, "quotes": out})
        _sweeps[venue] = {"at": now, "body": body}
        return body
