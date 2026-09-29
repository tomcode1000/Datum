"""Serve the oracle API and the replay UI from the standard library.

    python scripts/serve.py            # http://localhost:8000

    GET /                  replay UI
    GET /api/quote/TSLA    live quote: fair value, band, deviation, verdict
    GET /api/quotes        live quote for every ticker in the panel
    GET /api/panel         the fitted panel behind the model
"""
import json
import sys
import threading
import time
from dataclasses import asdict
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from oracle.service import quote, quote_all  # noqa: E402

# Quoting every ticker takes a few minutes under the upstream rate limit, too
# long to do inside a request. A background thread sweeps on a timer and
# /api/quotes serves the most recent finished sweep.
SWEEP_EVERY = 300
_sweep = {"body": None}


def _sweeper() -> None:
    while True:
        try:
            tickers = [t["ticker"] for t in
                       json.loads((ROOT / "panel.json").read_text())["tickers"]]
            out = [q if isinstance(q, dict) else asdict(q)
                   for q in quote_all(tickers)]
            _sweep["body"] = json.dumps({"at": int(time.time() * 1000),
                                         "every_s": SWEEP_EVERY, "quotes": out})
        except Exception as exc:          # keep the last good sweep
            print(f"sweep failed: {type(exc).__name__}: {exc}")
        time.sleep(SWEEP_EVERY)


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
            if _sweep["body"] is None:
                self._json(json.dumps({"pending": True}), status=503)
            else:
                self._json(_sweep["body"])
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
    threading.Thread(target=_sweeper, daemon=True).start()
    ThreadingHTTPServer(("", port), handler).serve_forever()


if __name__ == "__main__":
    main()
