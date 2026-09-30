"""Response plumbing for the hosted API (the Vercel functions in api/).

The hosted endpoints answer exactly what scripts/serve.py answers locally;
both call oracle.service, so the two cannot drift apart.
"""
import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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


def query(handler: BaseHTTPRequestHandler, name: str, default: str = "") -> str:
    return (parse_qs(urlparse(handler.path).query).get(name) or [default])[0]


def venue(handler: BaseHTTPRequestHandler) -> str:
    """The ?venue= of a request: solana (the default) or bitget."""
    v = query(handler, "venue", "solana").lower()
    if v not in ("solana", "bitget"):
        raise ValueError(f"unknown venue {v!r}; use solana or bitget")
    return v


def panel_file(v: str) -> Path:
    return ROOT / ("panel.json" if v == "solana" else f"panel-{v}.json")
