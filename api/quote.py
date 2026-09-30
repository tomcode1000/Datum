"""GET /api/quote/{ticker} (rewritten to /api/quote?ticker=...)."""
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from oracle.web import error, send, venue  # noqa: E402
from oracle.service import quote  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        ticker = (parse_qs(urlparse(self.path).query).get("ticker") or [""])[0]
        if not ticker:
            send(self, '{"error": "ticker required, e.g. /api/quote/TSLA"}', 400)
            return
        try:
            # A minute at the edge: a judge clicking "check live quote" twice
            # should not spend two rate-limited upstream calls.
            send(self, quote(ticker, venue=venue(self)).to_json(),
                 cache="public, s-maxage=60, stale-while-revalidate=120")
        except Exception as exc:
            error(self, exc)
