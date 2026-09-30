# Datum

*A weekend oracle for tokenized equities.*

**Tokenized US stocks trade 24/7. The market that prices them is open 32.5 hours
a week. This measures how wrong the on-chain price gets in the gap, and how long
it stays wrong.**

Every finding below is reproducible from three free, keyless public APIs. There
are no dependencies to install — the whole project is Python standard library.

```bash
python scripts/build_dataset.py    # fits both models, writes panel.json
python scripts/export_replay.py    # writes ui/replay.json
python scripts/serve.py            # http://localhost:8000
```

Hosted, the same page and API run on Vercel with no build step: `ui/` is served
statically and `api/` holds one Python function per endpoint, each calling
`oracle/service.py` exactly as the local server does (`vercel.json`).

---

## The problem

Between Friday's 16:00 ET close and Monday's 09:30 ET open, the US cash equity
market cannot reprice. CME index futures are shut for almost all of that window
too (Friday 17:00 ET to Sunday 18:00 ET). Pyth's standard equity feeds run an
overnight session Sunday–Thursday, so weeknights are already covered by free
infrastructure — **the weekend is the genuinely uncovered hole**, roughly 48
hours, every week.

Tokenized equities keep trading through it. Anything reading their on-chain price
during that window — a lending protocol valuing collateral, a liquidation engine,
a NAV process — is reading a price with no cash-market anchor behind it.

## What we measured

### 1. The 24/7 perp is an efficient reference

Before using Hyperliquid's equity perps as a reference, we checked whether their
weekend price discovery is real or noise. Across **21 weekends, 84 observations**
(TSLA, NVDA, AAPL, MSFT):

| metric | value |
|---|---|
| corr(weekend drift, realized Monday move) | **+0.855** |
| retention slope (1.0 = drift fully sticks) | **+1.048** |
| mean \|weekend drift\| | 1.36% (max 5.61%) |

Weekend drift on the perp is **fully retained through the Monday US open**. We
also split by BTC move size to test whether crypto flow contaminates it: it does
not — retention was 1.040 on low-BTC weekends and 1.104 on high-BTC weekends.

That is a **negative result against our original hypothesis**, which was that
weekend moves would be partly crypto-flow noise that reverts at the open. They
are not. The perp is doing genuine price discovery, which is precisely what makes
it usable as a reference.

### 2. Solana xStocks lag that reference, universally

Slope of the pool's forward return on its current deviation from the reference,
during weekend-gap hours only. Negative means the pool moves back toward the
reference.

| ticker | n | 1h | 6h | 12h | mean \|dev\| | pool liq | weekend vol |
|---|---|---|---|---|---|---|---|
| TSLA | 1551 | −0.723 | −0.935 | −1.133 | 16.9 bps | $1.59M | $5,889/hr |
| NVDA | 1547 | −0.684 | −0.685 | −0.869 | 17.9 bps | $2.89M | $6,418/hr |
| CRCL | 1562 | −0.638 | −0.838 | −1.236 | 18.6 bps | $2.22M | $17,705/hr |
| AMZN | 1372 | −0.768 | −0.862 | −0.840 | 23.3 bps | $250K | $381/hr |
| MSTR | 1528 | −0.647 | −0.680 | −0.774 | 27.7 bps | $1.14M | $2,839/hr |
| GOOGL | 1391 | −0.742 | −0.964 | −0.888 | 29.4 bps | $533K | $588/hr |
| AAPL | 1418 | −0.685 | −0.842 | −0.774 | 36.3 bps | $560K | $160/hr |
| META | 1261 | −0.443 | −0.515 | −0.467 | 37.5 bps | $930K | $195/hr |
| COIN | 748 | −0.761 | −0.681 | −0.885 | 52.4 bps | $1.23M | $1,235/hr |
| HOOD | 811 | −0.670 | −0.813 | −0.838 | 65.1 bps | $1.19M | $835/hr |
| SPCX | 691 | −0.833 | −0.951 | −0.931 | 70.1 bps | $1.95M | $1,499/hr |
| GME | 377 | −0.292 | −0.406 | −0.544 | 89.0 bps | $618K | $969/hr |
| PLTR | 821 | −0.372 | −0.541 | −0.677 | 91.7 bps | $329K | $100/hr |
| AVGO | 368 | −0.403 | −0.530 | −0.565 | 123.8 bps | $50K | $32/hr |

**All 16 tickers measured are negative at 1h** (two more, MSFT and STRC, are
excluded from fits for thin weekend samples — see Limitations). Mean 1h slope
**−0.627**, range −1.072 to −0.292.

**Why this is lag and not bid-ask bounce.** Measurement noise produces a large
negative slope at one hour that then *flattens toward zero* at longer horizons.
What we observe instead is convergence that **deepens monotonically with
horizon**, reaching full closure around 6–12h. On TSLA, across 5.5 months:

```
horizon:   1h      2h      3h      6h     12h
slope:  -0.718  -0.780  -0.808  -0.924  -1.116
```

The effect also survives restricting to economically meaningful deviations —
slope holds at ≈ −0.71 whether you filter to \|dev\| > 5, 10 or 20 bps.

### 3. Thinly-traded tokens are more mispriced

Across the 14 tickers with sufficient weekend samples:

```
corr(log weekend volume, mean |dev|)  = -0.652
corr(log pool liquidity, mean |dev|)  = -0.628

model: mean |dev| bps = 133.0 - 12.4 * ln(weekend hourly volume)   R2 = 0.42
   $100/hr    ->  76 bps
   $1,000/hr  ->  48 bps
   $10,000/hr ->  19 bps
```

Volume and pool TVL are **equally predictive**. We initially believed volume was
the sharper measure; on a 41-day window it appeared to be (−0.685 vs −0.412), but
that reversed once thin-sample tickers were excluded and the full history used.
**We make no claim that either dominates.**

### 4. Bitget rTokens: tighter, but slower to correct

The same measurement, run against Bitget's own tokenized stocks (rTokens, spot
pairs such as `RTSLAUSDT`), over the same weekends and the same reference:

| same 16 tickers | Solana xStocks | Bitget rTokens |
|---|---|---|
| tickers pulled back toward the reference at 1h | 16 of 16 | 16 of 16 |
| mean 1h convergence slope | −0.627 | −0.216 |
| mean \|deviation\| | 17–124 bps (14 fitted) | 12.5–35.4 bps |
| slope steeper on Solana | | 15 of 16 tickers |

Across all **77** rTokens with enough data, 68 are pulled back at 1h (mean
−0.304). Bitget's order book holds much closer to the reference than the Solana
pools do, but when it is off it corrects more slowly, and weekend volume barely
predicts by how much: the fitted band runs from about ±30 bps at $1,000/hr to
about ±19 bps at $1M/hr (R² 0.29, 61 tickers). Each venue is quoted against its
own fitted band; neither borrows the other's.

To rebuild: `python scripts/build_dataset.py bitget` then
`python scripts/export_replay.py bitget`, or run the *Build a venue's measured
panel* workflow on GitHub, which is how the committed files were made.

## What this is not

**It is not a trading strategy, and we checked.** Median weekend volume ranges
from **$32/hr (AVGO) to $17,705/hr (CRCL)**. At a mean dislocation of 17–124 bps,
round-trip DEX fees and slippage against that flow consume most or all of the
edge, and no meaningful size can be deployed without moving the price being
captured. Anyone presenting this as an arbitrage bot has not looked at the volume
column.

That is exactly why the inefficiency persists — and why the useful product is a
**pricing and risk layer**, not a trader.

## The product

`oracle/service.py` answers the three questions a consumer actually has:

```
GET /api/quote/TSLA
{
  "ticker": "TSLA",
  "verdict": "OK",              // OK | LAGGED | STALE | NO_POOL | NO_REFERENCE
  "weekend_gap": false,
  "reference": 381.83,          // fair value, from the 24/7 perp
  "pool": 380.82,               // the on-chain quote
  "deviation_bps": -26.4,
  "expected_bps": 26.7,         // typical for this token's liquidity
  "band_low": 381.32, "band_high": 382.34,
  "stale_hours": 0.4,
  "advice": "..."
}
```

Every GET takes `?venue=solana` (the default) or `?venue=bitget`, and
`/api/quote/` accepts the ticker, the xStock symbol (`TSLAx`) or the rToken
symbol (`RTSLAUSDT`). The answer also carries `venue` and `session` (`open`,
`overnight` or `weekend`, for the US cash market).

`GET /api/quotes` returns the same object for every ticker in the panel. A live
quote costs one Hyperliquid call and one GeckoTerminal call for all pools at
once; a pool that has not traded within the hour costs one more call for its
exact last trade. The mint and pool addresses come from `pools.json`
(`python scripts/resolve_pools.py`), so no lookups are spent on them. A sweep
is held for five minutes, in the service and at the CDN when hosted.

`stale_hours` is exact once a pool has been quiet for over an hour, which is
where the `STALE` verdict is decided. For an active pool it is the shortest
activity window holding a trade (5, 15, 30 or 60 minutes), so an upper bound.

The band **adapts to liquidity**: TSLA at $5,889/hr gets ±27 bps, AVGO at $32/hr
gets ±90 bps. `STALE` is a distinct verdict from `LAGGED` on purpose — below a
certain flow a pool is not lagging, it simply has no price, and a consumer needs
to tell those apart.

### Ask Datum (Qwen)

`POST /api/ask {"question": "Can I liquidate TSLA on Bitget right now?"}` answers a
question in plain English. `oracle/ask.py` gives Qwen (`qwen/qwen3.8-flash` on
OpenRouter in the hosted demo; the hackathon's endpoint at
`hackathon.bitgetops.com/v1` works too, set by `LLM_BASE_URL` / `LLM_MODEL`) the
live verdicts on both venues, the measured history behind each and the venue
comparisons computed from it, and asks it to explain them and end with an
action. Reasoning is switched off: the verdict is already decided.

The model explains; Datum decides. It **fails closed**: with no key, a failed
call, or an answer that names a verdict Datum did not return, the reply is
Datum's own advice, marked as such. The model never sees a way to change a
verdict, and an answer that tries is withheld.

Who this is for: lending protocols setting collateral haircuts, liquidation
engines deciding whether a weekend move is real, NAV and portfolio marks, and
venues carrying tokenized equity risk over weekends.

## Demo

The UI replays **historical** weekends rather than showing live state, so it is
equally legible at 3am on a Wednesday as on a Sunday night — which matters,
because judging happens whenever judging happens. Pick a ticker, pick from up to
24 weekends, and see the reference, the pool, the expected band, and the Monday
open marked.

The live-quote panel is deliberately secondary. During US market hours it
correctly reports small deviations inside the band, which demonstrates the tool
discriminates rather than crying wolf.

## Data sources

| source | what | auth |
|---|---|---|
| Hyperliquid `info` API | 24/7 equity perps, HIP-3 builder dex `xyz` | none |
| Jupiter token search | resolves an xStocks symbol to its Solana mint | none |
| GeckoTerminal | hourly OHLCV per pool, ~5.5 months reachable | none |
| Bitget spot API | rTokens: hourly candles, live tickers, last trade | none |
| Qwen (hackathon endpoint) | Ask Datum's written answers only; never a verdict | key, server-side |

**Counterfeit tokens.** A search for `TSLAx` returns four fake mints alongside
the real one, some priced around $0.000005. Genuine xStocks mints use an `Xs`
vanity prefix, which `oracle/sources.py` enforces. This is a safety filter, not a
nicety — pricing off a counterfeit mint is a live failure mode for anything
consuming Solana token data by symbol.

## Limitations

- **`DEV_CAP = 0.05`** — deviations beyond 5% are discarded as thin-pool
  artefacts. A single trade against a shallow curve printed a 1,374 bps "close"
  in raw data. Keeping such bars lets a handful dominate every regression. This
  is a modelling choice that changes the numbers.
- **Thin weekend samples excluded from fits.** STRC (67 obs, 390 bps mean
  deviation, *positive* convergence) and MSFT (132 obs) are shown in the table
  but excluded from cross-sectional fits. Including them moved
  corr(log volume, \|dev\|) from −0.65 to −0.42 and R² from 0.42 to 0.18.
- **Point estimates are sample-period dependent.** TSLA's 1h slope is −0.718 over
  5.5 months and −0.973 over 41 days. The *sign* and the *ordering* across
  tickers are stable; the magnitudes are not. Quote ranges, not single numbers.
- **R² ≈ 0.42, and it moves** (0.18–0.42 depending on filtering). The liquidity
  model is indicative, not a precision instrument.
- **The model does not extrapolate.** `deviation_bps()` clamps to the fitted
  volume range; the log fit predicts negative mispricing above ~$50k/hr.
- **Market holidays are not handled.** A Monday holiday means the "open"
  timestamp has no cash-market print behind it.
- **The reference is a perp, not the cash market.** Hyperliquid's own
  documentation notes tracking error varies by ticker. Section 1 establishes the
  reference is efficient enough to use; it is not ground truth.
- **n = 14–16 tickers.** A −0.65 cross-sectional correlation on 14 points is
  suggestive, not conclusive.
- **Bitget's band is nearly flat.** On rTokens, weekend volume explains little
  of the deviation (R² 0.29 across 61 tickers), so the band there is close to a
  constant ~±20–30 bps. The page shows the 16 tickers both venues share; the
  full 77-ticker table is in `panel-bitget.json`.
- **Bitget's last trade is known to the hour.** Its candles are hourly, so an
  rToken's `stale_hours` is counted from the end of its last traded hour, a
  lower bound.
- **Ask Datum's prose is a model's.** The verdicts and figures it quotes come
  from Datum; the sentences around them are Qwen's, checked only for naming a
  verdict Datum did not return and for ending with an action.

## Layout

```
oracle/
  http.py       retry, backoff, on-disk cache (history TTL 12h)
  calendar.py   US market hours; explicit DST rules, no tzdata needed
  sources.py    Hyperliquid / Jupiter / GeckoTerminal / Bitget
  dataset.py    weekend-gap alignment into observations
  model.py      convergence fit per horizon; liquidity -> deviation model
  service.py    the oracle: fair value, band, staleness, verdict, per venue
  ask.py        Ask Datum: Qwen explains the verdicts, fails closed
  web.py        shared plumbing for the hosted API
scripts/
  build_dataset.py   fit and write panel.json (or panel-bitget.json)
  sensitivity.py     how much the claims depend on ticker filtering
  export_replay.py   write ui/replay.json (or ui/replay-bitget.json)
  resolve_pools.py   write pools.json, the Solana mint and pool per ticker
  record_run.py      append a live sweep to runs/ (hourly, via GitHub Actions)
  serve.py           API + UI on the standard library
api/                 one Vercel function per endpoint
ui/index.html        the site: replay, live quotes, Ask Datum, both venues
```
