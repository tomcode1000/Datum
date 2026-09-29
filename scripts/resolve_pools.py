"""Resolve each panel ticker to its genuine xStocks mint and deepest pool.

    python scripts/resolve_pools.py    # writes pools.json

Mints and pools do not move, so the live quote reads them from pools.json
instead of spending two rate-limited lookups per ticker on every request.
Rerun it only when a ticker is added to the panel.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from oracle.sources import xstock_mint, xstock_pool  # noqa: E402


def main() -> None:
    tickers = [t["ticker"] for t in
               json.loads((ROOT / "panel.json").read_text())["tickers"]]
    out = {}
    for t in tickers:
        found = xstock_mint(t)
        pool = xstock_pool(found[0]) if found else None
        if pool:
            out[t] = {"mint": found[0], "pool": pool}
        print(f"{t:6} {pool or 'no genuine pool'}")
        time.sleep(1)
    (ROOT / "pools.json").write_text(json.dumps(out, indent=2) + "\n")
    print(f"pools.json: {len(out)} of {len(tickers)} tickers")


if __name__ == "__main__":
    main()
