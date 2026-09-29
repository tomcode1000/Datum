"""Align the Hyperliquid reference against xStocks pool prices.

One observation = one hour inside a weekend gap, for one ticker, carrying the
deviation of the pool price from the reference plus the pool's forward returns.
Those forward returns are what let us measure convergence.
"""
from dataclasses import dataclass

from .calendar import in_weekend_gap
from .sources import (hl_candles, xstock_candles, xstock_mint, xstock_pool)

HORIZONS = (1, 6, 12)
HOUR_MS = 3_600_000

# Deviations beyond this are thin-pool artefacts, not prices: a single trade
# against a shallow curve can print a "close" 13%+ away from the reference.
# Keeping them would let a handful of bad bars dominate every regression.
DEV_CAP = 0.05

MIN_BARS = 300          # below this a pool is too sparse to model
MIN_LIQUIDITY = 20_000  # ignore dust markets entirely

# A pool can clear MIN_BARS on weekday activity yet still yield almost no
# weekend observations. Those tickers produce unstable per-ticker estimates and,
# on a cross-section of ~15 points, can dominate the fit outright: including
# STRC (67 obs, 390bps mean deviation, positive convergence) and MSFT (132 obs)
# moved corr(log volume, |dev|) from -0.65 to -0.42 and R2 from 0.42 to 0.18.
# They stay in the per-ticker table, flagged, but are excluded from any fit.
MIN_CROSS_SECTION_OBS = 200


@dataclass
class Obs:
    ticker: str
    ts: int
    reference: float
    pool: float
    deviation: float          # pool / reference - 1
    volume: float             # pool USD volume that hour
    forward: dict[int, float] # horizon hours -> pool return


@dataclass
class Pair:
    ticker: str
    liquidity: float
    obs: list[Obs]

    @property
    def median_volume(self) -> float:
        if not self.obs:
            return 0.0
        v = sorted(o.volume for o in self.obs)
        return v[len(v) // 2]

    @property
    def reliable(self) -> bool:
        """Enough weekend observations to trust in a cross-sectional fit."""
        return len(self.obs) >= MIN_CROSS_SECTION_OBS

    @property
    def mean_abs_deviation(self) -> float:
        if not self.obs:
            return 0.0
        return sum(abs(o.deviation) for o in self.obs) / len(self.obs)


def build_pair(ticker: str, pages: int = 4) -> Pair | None:
    """Assemble weekend-gap observations for one ticker, or None if unusable."""
    found = xstock_mint(ticker)
    if not found:
        return None
    mint, liquidity = found
    if liquidity < MIN_LIQUIDITY:
        return None
    pool = xstock_pool(mint)
    if not pool:
        return None

    pool_bars = xstock_candles(pool, pages=pages)
    if len(pool_bars) < MIN_BARS:
        return None

    lo, hi = min(pool_bars), max(pool_bars) + HOUR_MS
    ref_bars = hl_candles(ticker, lo, hi)

    obs: list[Obs] = []
    for ts in sorted(set(pool_bars) & set(ref_bars)):
        if not in_weekend_gap(ts):
            continue
        price, volume = pool_bars[ts]
        reference = ref_bars[ts]
        if reference <= 0 or price <= 0:
            continue
        deviation = price / reference - 1
        if abs(deviation) > DEV_CAP:
            continue
        forward = {}
        for h in HORIZONS:
            later = pool_bars.get(ts + h * HOUR_MS)
            if later:
                forward[h] = later[0] / price - 1
        if not forward:
            continue
        obs.append(Obs(ticker, ts, reference, price, deviation, volume, forward))

    return Pair(ticker, liquidity, obs) if obs else None
