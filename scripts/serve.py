"""Serve the oracle API and the replay UI from the standard library.

    python scripts/serve.py            # http://localhost:8000

    GET /                  replay UI
    GET /api/quote/TSLA    live quote: fair value, band, deviation, verdict
    GET /api/quotes        live quote for every ticker in the panel
    GET /api/panel         the fitted panel behind the model
"""
import json
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from oracle.service import quote, sweep_json  # noqa: E402


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/quote/"):
            ticker = self.path.rsplit("/", 1)[-1]
            try:
                self._json(quote(ticker).to_json())
            except Exception as exc:
                self._json(json.dumps({"error": f"{type(exc).__name__}: {exc}"}),
                           status=500)
            return
        if self.path == "/api/quotes":
            try:
                self._json(sweep_json())
            except Exception as exc:
                self._json(json.dumps({"error": f"{type(exc).__name__}: {exc}"}),
                           status=500)
            return
        if self.path == "/api/panel":
            self._json((ROOT / "panel.json").read_text())
            return
        super().do_GET()

    def _json(self, body: str, status: int = 200):
        payload = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        pass          # keep the demo console clean


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    handler = partial(Handler, directory=str(ROOT / "ui"))
    print(f"datum on http://localhost:{port}")
    print(f"  UI     http://localhost:{port}/")
    print(f"  quote  http://localhost:{port}/api/quote/TSLA")
    print(f"  all    http://localhost:{port}/api/quotes")
    ThreadingHTTPServer(("", port), handler).serve_forever()


if __name__ == "__main__":
    main()
