"""Response plumbing for the hosted API (the Vercel functions in api/).

The hosted endpoints answer exactly what scripts/serve.py answers locally;
both call oracle.service, so the two cannot drift apart.
"""
import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def send(handler: BaseHTTPRequestHandler, body: str, status: int = 200,
         cache: str = "no-store") -> None:
    payload = body.encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Cache-Control", cache)
    handler.end_headers()
    handler.wfile.write(payload)


def error(handler: BaseHTTPRequestHandler, exc: Exception) -> None:
    send(handler, json.dumps({"error": f"{type(exc).__name__}: {exc}"}), 500)
