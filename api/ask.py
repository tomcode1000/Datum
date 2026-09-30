"""POST /api/ask {question, ticker?} - Ask Datum, answered by Qwen from Datum's facts."""
import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from oracle.web import error, send  # noqa: E402
from oracle.ask import ask  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 16384)
            body = json.loads(self.rfile.read(n) or b"{}")
            out = ask(str(body.get("question", "")), body.get("ticker"),
                      body.get("positions"), body.get("history"))
            send(self, json.dumps(out), status=400 if "error" in out else 200)
        except Exception as exc:
            error(self, exc)
