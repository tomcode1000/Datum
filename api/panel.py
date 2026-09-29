"""GET /api/panel - the fitted panel behind the liquidity model."""
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from oracle.web import ROOT, send  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        send(self, (ROOT / "panel.json").read_text(),
             cache="public, s-maxage=3600")
