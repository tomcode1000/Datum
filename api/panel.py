"""GET /api/panel - the fitted panel behind the liquidity model."""
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from oracle.web import error, panel_file, send, venue  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            send(self, panel_file(venue(self)).read_text(),
                 cache="public, s-maxage=3600")
        except Exception as exc:
            error(self, exc)
