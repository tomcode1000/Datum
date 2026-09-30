"""Serve the oracle API and the replay UI from the standard library.

    python scripts/serve.py            # http://localhost:8000

    GET /                  replay UI
    GET /api/quote/TSLA    live quote: fair value, band, deviation, verdict
    GET /api/quotes        live quote for every ticker in the panel
    GET /api/panel         the fitted panel behind the model
    POST /api/ask          Ask Datum: {"question": ..., "ticker": ...}
    (every GET takes ?venue=solana|bitget; Solana is the default)
"""
import json
import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Local runs read secrets from .env (gitignored); the host sets them itself.
_env = ROOT / ".env"
if _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _k, _, _v = _line.partition("=")
        if _k.strip() and not _k.startswith("#") and _v.strip():
            os.environ.setdefault(_k.strip(), _v.strip())

from oracle.ask import ask  # noqa: E402
from oracle.service import quote, sweep_json  # noqa: E402


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path, _, qs = self.path.partition("?")
        v = (parse_qs(qs).get("venue") or ["solana"])[0].lower()
        if path.startswith("/api/quote/"):
            ticker = path.rsplit("/", 1)[-1]
            try:
                self._json(quote(ticker, venue=v).to_json())
            except Exception as exc:
                self._json(json.dumps({"error": f"{type(exc).__name__}: {exc}"}),
                           status=500)
            return
        if path == "/api/quotes":
            try:
                self._json(sweep_json(v))
            except Exception as exc:
                self._json(json.dumps({"error": f"{type(exc).__name__}: {exc}"}),
                           status=500)
            return
        if path == "/api/panel":
            name = "panel.json" if v == "solana" else f"panel-{v}.json"
            try:
                self._json((ROOT / name).read_text())
            except OSError as exc:
                self._json(json.dumps({"error": str(exc)}), status=404)
            return
        super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0] != "/api/ask":
            self._json(json.dumps({"error": "not found"}), status=404)
            return
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 4096)
            body = json.loads(self.rfile.read(n) or b"{}")
            out = ask(str(body.get("question", "")), body.get("ticker"))
            self._json(json.dumps(out), status=400 if "error" in out else 200)
        except Exception as exc:
            self._json(json.dumps({"error": f"{type(exc).__name__}: {exc}"}), status=500)

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
