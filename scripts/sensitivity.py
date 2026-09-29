"""How much do the cross-sectional claims depend on which tickers we keep?

Thin-sample tickers can dominate a 16-point regression, so before quoting any
correlation we check it against a minimum-observation filter.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from oracle.model import pearson  # noqa: E402

rows = json.loads((Path(__file__).resolve().parent.parent / "panel.json").read_text())["tickers"]

print(f"{'min obs':>8}{'n':>4}{'corr vol':>10}{'corr liq':>10}{'R2 vol':>8}"
      f"{'mean 1h':>9}  excluded")
for min_obs in (0, 200, 300, 500, 700):
    keep = [r for r in rows if r["n"] >= min_obs and r["median_weekend_volume"] > 0]
    if len(keep) < 5:
        continue
    lv = [math.log(r["median_weekend_volume"]) for r in keep]
    ll = [math.log(r["liquidity"]) for r in keep]
    dv = [r["mean_abs_dev_bps"] for r in keep]
    s1 = [r["convergence"]["1"] for r in keep if r["convergence"]["1"] is not None]
    cv, cl = pearson(lv, dv), pearson(ll, dv)
    dropped = sorted(r["ticker"] for r in rows if r not in keep)
    print(f"{min_obs:>8}{len(keep):>4}{cv:>+10.3f}{cl:>+10.3f}{cv*cv:>8.2f}"
          f"{sum(s1)/len(s1):>+9.3f}  {','.join(dropped) or '-'}")

print("\nper-ticker, sorted by sample size:")
print(f"{'ticker':9}{'n':>6}{'|dev|bps':>10}{'vol$/hr':>10}{'1h':>8}")
for r in sorted(rows, key=lambda r: r["n"]):
    print(f"{r['ticker']:9}{r['n']:>6}{r['mean_abs_dev_bps']:>10.1f}"
          f"{r['median_weekend_volume']:>10,.0f}{r['convergence']['1']:>+8.3f}")
