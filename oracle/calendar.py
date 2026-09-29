"""US equity market hours, and the weekend gap we actually care about.

Earlier prototypes for this project hardcoded EDT (UTC-4), which silently
breaks once US daylight saving ends in November. We implement the US DST rules
instead of using zoneinfo, because Windows ships no system tz database and we
want this repo to run with no third-party installs at all.

The "weekend gap" is the stretch when the US cash market is shut and cannot
reopen until Monday: Friday's 16:00 ET close through Monday's 09:30 ET open.
CME index futures are shut for almost all of it too (Friday 17:00 ET to Sunday
18:00 ET), which is why crypto-native venues are the only continuous price
source in this window.
"""
import datetime as dt

UTC = dt.timezone.utc
_STD = dt.timedelta(hours=-5)   # EST
_DST = dt.timedelta(hours=-4)   # EDT

MARKET_OPEN = dt.time(9, 30)
MARKET_CLOSE = dt.time(16, 0)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> int:
    """Day-of-month of the nth given weekday (Monday=0)."""
    first = dt.date(year, month, 1).weekday()
    return 1 + ((weekday - first) % 7) + (n - 1) * 7


class _Eastern(dt.tzinfo):
    """US Eastern time under the post-2007 rules.

    DST runs from 02:00 local on the second Sunday of March to 02:00 local on
    the first Sunday of November. Ambiguous and non-existent local times inside
    the transition hour are not disambiguated; market hours never fall in it.
    """

    def utcoffset(self, when):
        return _STD + self.dst(when)

    def dst(self, when):
        if when is None:
            return dt.timedelta(0)
        start = dt.datetime(when.year, 3,
                            _nth_weekday(when.year, 3, 6, 2), 2)
        end = dt.datetime(when.year, 11,
                          _nth_weekday(when.year, 11, 6, 1), 2)
        naive = when.replace(tzinfo=None)
        return dt.timedelta(hours=1) if start <= naive < end else dt.timedelta(0)

    def tzname(self, when):
        return "EDT" if self.dst(when) else "EST"


NY = _Eastern()


def to_ny(ts_ms: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(ts_ms / 1000, UTC).astimezone(NY)


def ms(d: dt.datetime) -> int:
    return int(d.timestamp() * 1000)


def in_weekend_gap(ts_ms: int) -> bool:
    """True when the US cash market is shut for the weekend.

    Deliberately excludes weeknight overnights: Pyth already publishes an
    overnight equity session Sunday-Thursday, so weeknights are covered by
    existing free infrastructure. The weekend is the genuinely uncovered hole.
    """
    d = to_ny(ts_ms)
    wd = d.weekday()
    if wd == 4:
        return d.time() >= MARKET_CLOSE
    if wd in (5, 6):
        return True
    if wd == 0:
        return d.time() < MARKET_OPEN
    return False


def weekend_windows(start_ms: int, end_ms: int):
    """Yield (friday_close, monday_open) in epoch ms for each weekend spanned.

    Holidays are not handled: a Monday holiday means the "open" timestamp has
    no cash-market print behind it. Callers needing the official open should
    validate against an equity source; the crypto venue trades through it.
    """
    d = to_ny(start_ms).date()
    last = to_ny(end_ms).date()
    while d <= last:
        if d.weekday() == 4:
            close = dt.datetime.combine(d, MARKET_CLOSE, tzinfo=NY)
            open_ = dt.datetime.combine(d + dt.timedelta(days=3),
                                        MARKET_OPEN, tzinfo=NY)
            if ms(close) >= start_ms and ms(open_) <= end_ms:
                yield ms(close), ms(open_)
        d += dt.timedelta(days=1)
