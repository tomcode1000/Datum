"""The three free, keyless data sources this project runs on.

Hyperliquid  - 24/7 equity perps (HIP-3 builder dex "xyz", assets namespaced
               as "xyz:TSLA"). Our weekend reference price. Empirically these
               are efficient: weekend drift is retained through the Monday US
               open (slope ~1.05, r~0.86 over 21 weekends), so the perp is a
               valid reference rather than something to arbitrage against.
Jupiter      - resolves an xStocks symbol to its Solana mint.
GeckoTerminal- hourly OHLCV for the xStocks pool. ~5.5 months of history is
               reachable by paging backwards, which is far more than the 30
               days a Bitquery free tier would give.

No API keys anywhere. GeckoTerminal allows ~30 req/min, so oracle.http caches
every response to disk and callers should page politely.
"""
import time

from .http import get, is_cached, post

HL_INFO = "https://api.hyperliquid.xyz/info"
HL_DEX = "xyz"
JUP = "https://lite-api.jup.ag/tokens/v2/search"
GT = "https://api.geckoterminal.com/api/v2/networks/solana"

# xStocks mints use an "Xs" vanity prefix. This is a safety filter, not a
# nicety: a search for TSLAx returns four counterfeit mints alongside the
# real one, some priced around $0.000005.
XSTOCK_PREFIX = "Xs"

_CHUNK_MS = 45 * 86_400_000  # Hyperliquid caps candles per request

# Historical bars never change; only the newest one does. A short TTL made every
# rerun re-fetch five months of settled history and pay the rate-limit pauses
# again, so iterating cost ~4 minutes. Half a day keeps same-day work instant
# while still picking up new weekends on the next day's first run.
_HISTORY_TTL = 43_200


def hl_universe() -> list[str]:
    """Ticker names listed on the builder dex, without the 'xyz:' prefix."""
    meta = post(HL_INFO, {"type": "meta", "dex": HL_DEX}, max_age=86_400)
    return [u["name"].split(":")[-1] for u in meta["universe"]]


def hl_context() -> dict[str, dict]:
    """Live mark/oracle/funding/open-interest per ticker. Not cached."""
    meta, ctxs = post(HL_INFO, {"type": "metaAndAssetCtxs", "dex": HL_DEX},
                      cache=False)
    return {u["name"].split(":")[-1]: c
            for u, c in zip(meta["universe"], ctxs)}


def hl_candles(ticker: str, start_ms: int, end_ms: int) -> dict[int, float]:
    """Hourly closes for an equity perp, keyed by bar-open epoch ms."""
    out: dict[int, float] = {}
    cur = start_ms
    while cur < end_ms:
        nxt = min(cur + _CHUNK_MS, end_ms)
        bars = post(HL_INFO, {"type": "candleSnapshot", "req": {
            "coin": f"{HL_DEX}:{ticker}", "interval": "1h",
            "startTime": cur, "endTime": nxt}}, max_age=_HISTORY_TTL)
        for b in bars:
            out[b["t"]] = float(b["c"])
        cur = nxt
    return out


def xstock_mint(ticker: str) -> tuple[str, float] | None:
    """Resolve e.g. 'TSLA' -> (mint, usd_liquidity) for the real TSLAx token.

    Returns None when no genuine xStock exists, which is the normal case for
    the commodity and non-US tickers the builder dex also lists.
    """
    symbol = f"{ticker}x"
    for t in get(f"{JUP}?query={symbol}", max_age=86_400):
        if (str(t.get("id", "")).startswith(XSTOCK_PREFIX)
                and str(t.get("symbol", "")).upper() == symbol.upper()):
            return t["id"], float(t.get("liquidity") or 0.0)
    return None


def xstock_pool(mint: str) -> str | None:
    """Deepest Solana pool for a mint, by USD reserves."""
    pools = get(f"{GT}/tokens/{mint}/pools", max_age=86_400)["data"]
    if not pools:
        return None
    deepest = max(pools, key=lambda p:
                  float(p["attributes"].get("reserve_in_usd") or 0))
    return deepest["id"].split("_")[-1]


def xstock_candles(pool: str, pages: int = 4,
                   polite: float = 4.0) -> dict[int, tuple[float, float]]:
    """Hourly (close, volume_usd) for a pool, paging backwards through history.

    Each page is up to 1000 hourly bars (~41 days). Four pages reaches roughly
    5.5 months, which covers the full life of the equity perps so far.
    """
    out: dict[int, tuple[float, float]] = {}
    before = int(time.time())
    for page in range(pages):
        url = (f"{GT}/pools/{pool}/ohlcv/hour"
               f"?aggregate=1&limit=1000&before_timestamp={before}")
        cached = is_cached(url, max_age=_HISTORY_TTL)
        rows = get(url, max_age=_HISTORY_TTL)["data"]["attributes"]["ohlcv_list"]
        if not rows:
            break
        for ts, _o, _h, _l, close, vol in rows:
            out[ts * 1000] = (float(close), float(vol))
        before = min(r[0] for r in rows) - 1
        if not cached and page < pages - 1:   # pause between pages, not after
            time.sleep(polite)
    return out


# Activity windows GeckoTerminal reports per pool, shortest first, in hours.
ACTIVITY_WINDOWS = (("m5", 5 / 60), ("m15", 0.25), ("m30", 0.5), ("h1", 1.0))


def xstock_pools_live(pools: list[str]) -> dict[str, dict]:
    """Current price and trade activity for many pools, one request per 30.

    Live quoting used to fetch a page of candles per ticker; sixteen of those
    in a burst ran straight into the 30/min limit. This is one call."""
    out: dict[str, dict] = {}
    for i in range(0, len(pools), 30):
        chunk = pools[i:i + 30]
        data = get(f"{GT}/pools/multi/{','.join(chunk)}", cache=False,
                   tries=3, pause=3.0)["data"]
        for d in data:
            out[d["id"].split("_")[-1]] = d["attributes"]
    return out


def pool_last_trade_ms(pool: str) -> int | None:
    """Epoch ms of the pool's most recent trade within the last 24h, or None."""
    rows = get(f"{GT}/pools/{pool}/trades", cache=False,
               tries=3, pause=3.0)["data"]
    stamps = [_iso_ms(r["attributes"]["block_timestamp"]) for r in rows]
    return max(stamps) if stamps else None


def _iso_ms(stamp: str) -> int:
    from datetime import datetime
    return int(datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() * 1000)
