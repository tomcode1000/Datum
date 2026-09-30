# Research walkthrough: can a lender trust TSLAx on a Saturday?

One complete research task in Datum, from a question to a decision. Every
figure below comes from the project's own data and can be checked on the live
site: **https://datum-sandy.vercel.app**

## The question

A lending protocol accepts TSLAx (tokenized Tesla on Solana) as collateral. It is
Friday evening. The Nasdaq is closed until Monday 09:30 ET, but TSLAx keeps
trading on-chain. If a borrower's position needs to be valued or liquidated over
the weekend, **can the protocol use the on-chain pool price?**

## Step 1. Look at a real weekend

Open the site, pick **TSLA** and the weekend of **18 Sep 2026**. The chart shows
the on-chain pool against the Hyperliquid 24/7 TSLA perp, hour by hour, from the
Friday close to the Monday open (66 hourly points).

What that weekend shows:

| Figure | Value |
|---|---|
| Widest gap | **+58 bps**, Friday 18:00 ET (pool $365.88 vs reference $363.76) |
| Expected band for TSLA's liquidity | **±26 bps** |
| Hours outside the band | **28 of 66** |
| Gap at the Monday open | −28 bps |

So for 28 hours of that weekend the pool price sat outside the range the pool's
own liquidity would predict.

## Step 1b. Same weekend, Bitget's own rToken

Switch the header to **Bitget rTokens** and pick the same weekend. RTSLAUSDT,
measured against the same reference:

| Figure | Solana xStock | Bitget rToken |
|---|---|---|
| Widest gap | +58 bps | +39 bps |
| Hours outside the band | 28 of 66 | 7 of 56 hours with trades |
| Gap at the Monday open | −28 bps | about −1 bp |

Bitget holds much closer to the reference. Across the 16 tickers both venues
share it stays tighter (12.5 to 35.4 bps typical) but corrects more slowly (1h
slope −0.216 against −0.627; slower on 15 of 16 tickers).

## Step 2. Check the reference is worth trusting

A gap only matters if the reference is right. Datum checked this before relying
on it: across **21 weekends and 84 observations**, weekend moves on the
Hyperliquid perp were kept through the Monday US open (retention **1.048**,
correlation **0.855**). The perp is doing real price discovery over the weekend,
so it is a sound reference. Details on the Methodology page.

## Step 3. Check the gap closes, and how fast

If the pool is lagging rather than just noisy, it should move back toward the
reference. The Measurement page shows the 1h convergence slope: for TSLA it is
**−0.723**, and it is negative for **every** ticker measured (mean −0.627). The
slope gets steeper at 6h and 12h, which is lag closing, not bid-ask bounce.

## Step 4. Ask Datum right now

```
GET https://datum-sandy.vercel.app/api/quote/TSLA
```

The answer carries the reference price, the pool price, the deviation, the
expected band, how long since the pool last traded, and a verdict with plain
advice. The Cross-ticker page shows the same answer for all 16 tickers at once
(`/api/quotes`).

## Step 4b. Ask it, about your own position

Open **Ask Datum**, add the position (TSLA, Bitget, 100, liquidation at $330) and
press **Check my positions**. Datum marks it at the price it trusts, works out
its value and its distance to liquidation, and Qwen explains the result in plain
English, ending with the action. A follow-up ("And on the other venue?") keeps
the context. Datum decides and the model explains: an answer that names a
verdict Datum did not return is withheld and Datum's own advice is shown.

## Step 5. The decision

| Verdict | What the protocol should do |
|---|---|
| **OK** | Use the pool price. |
| **LAGGED** | Value the collateral from the reference, not the pool, until it converges (typically 1 to 12 hours). |
| **STALE** | The pool has not traded for over 3 hours. Treat its price as missing and use the reference. |
| **NO_POOL** | Use the reference only. Never quote a pool found by symbol search: a search for TSLAx returns four counterfeits. |
| **NO_REFERENCE** | Hold any action that needs a price. |

**Actionable insight:** on the weekend of 18 Sep, a liquidation engine reading
the TSLAx pool would have been working from a price up to 58 bps wrong, and
outside the expected band for 28 hours. On a $1M position that is about $5,840
of mispricing at the widest point (arithmetic on the figures above, not a
measured loss). Datum would have returned LAGGED for those hours and pointed the
protocol at the reference instead.

Thin tokens are worse. AVGO trades about $32 an hour on weekends; its expected
band is ±90 bps, and it came back STALE in live checks on 29 Sep 2026. Treat
its weekend pool price with the most suspicion of any ticker in the panel.

## What not to do with this

Datum is a pricing check, not a trading signal. The gaps look like free money
but are not: with median weekend volume between $32 and $17,705 an hour, fees and
slippage eat the 17 to 124 bps edge. It tells you which price to trust. It does
not tell you to trade.
