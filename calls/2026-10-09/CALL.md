# Weekend call, made Fri 09 Oct 2026 23:58 UTC

Committed at the Friday close, before the weekend it predicts. Scored after the
Monday open by `scripts/weekend_call.py score`, whichever way it comes out.

## Predictions

1. **drift**: Over the weekend the tokens drift: on each venue, the median |deviation| across all weekend ticker-hours is larger than the median |deviation| at the Friday close.
2. **convergence**: After the Monday open they come back: on each venue, the median |deviation| one hour after the open is smaller than the weekend median.
3. **pullback**: Tokens outside their band just before the open are pulled toward the reference: on each venue, at least half of them are closer to it one hour after the open.

## Friday close

| Venue | Tickers quoted | Median abs deviation | Outside band |
|---|---|---|---|
| solana | 16 | 29.8 bps | 6 |
| bitget | 16 | 1.4 bps | 0 |
