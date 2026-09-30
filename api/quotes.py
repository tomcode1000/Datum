"""GET /api/quotes - a live quote for every ticker in the panel."""
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from oracle.web import error, send, venue  # noqa: E402
from oracle.service import SWEEP_TTL, sweep_json  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # The edge holds a sweep for the same five minutes the service
            # does, so every visitor in that window shares one upstream pass.
            send(self, sweep_json(venue(self)), cache=f"public, s-maxage={SWEEP_TTL}, "
                                           f"stale-while-revalidate={SWEEP_TTL}")
        except Exception as exc:
            error(self, exc)
