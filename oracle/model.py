"""Two fits: how fast a deviation closes, and how large it is to begin with."""
import math

from .dataset import HORIZONS, Pair


def ols(xs: list[float], ys: list[float]) -> float | None:
    """Slope of y on x. None when there is too little to fit."""
    n = len(xs)
    if n < 40:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return 0.0 if dx * dy == 0 else sum(
        (x - mx) * (y - my) for x, y in zip(xs, ys)) / (dx * dy)


def convergence(pair: Pair) -> dict[int, float | None]:
    """Slope of forward pool return on current deviation, per horizon.

    Negative means the pool moves back toward the reference. A slope that
    deepens with horizon is genuine lag; measurement noise would instead
    reverse fully at one hour and then flatten.
    """
    out = {}
    for h in HORIZONS:
        pts = [(o.deviation, o.forward[h]) for o in pair.obs if h in o.forward]
        out[h] = ols([d for d, _ in pts], [f for _, f in pts]) if pts else None
    return out


class LiquidityModel:
    """mean |deviation| = a + b * ln(weekend hourly volume).

    Fitted across tickers, so it answers the question a lending protocol
    actually has: given how thinly this token trades at the weekend, how wrong
    is its quoted price likely to be?

    Treat this as indicative, not precise. R2 lands near 0.3-0.4 depending on
    which tickers are included, and weekend volume is no sharper a predictor
    than pool TVL (both correlate about -0.63 with mean deviation), so no claim
    should be made that one dominates the other.
    """

    def __init__(self, a: float, b: float, r2: float, lo: float, hi: float):
        self.a, self.b, self.r2 = a, b, r2
        self.lo, self.hi = lo, hi   # fitted volume range

    @classmethod
    def fit(cls, pairs: list[Pair]) -> "LiquidityModel":
        usable = [p for p in pairs if p.median_volume > 0 and p.reliable]
        xs = [math.log(p.median_volume) for p in usable]
        ys = [p.mean_abs_deviation for p in usable]
        b = ols(xs, ys) if len(xs) >= 40 else _small_slope(xs, ys)
        a = sum(ys) / len(ys) - b * (sum(xs) / len(xs))
        r = pearson(xs, ys)
        vols = [p.median_volume for p in usable]
        return cls(a, b, r * r, min(vols), max(vols))

    def deviation_bps(self, weekend_hourly_volume: float) -> float:
        v = min(max(weekend_hourly_volume, self.lo), self.hi)  # no extrapolating
        return (self.a + self.b * math.log(v)) * 10_000


def _small_slope(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
