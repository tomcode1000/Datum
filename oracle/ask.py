"""Ask Datum: a question in plain English, answered by Qwen from Datum's facts.

The division of labour is strict. Datum measures and decides: the verdicts come
from oracle/service.py, a fitted model and fixed rules, and are the same for the
same data every time. Qwen only explains: it gets those verdicts and the measured
figures behind them, and writes the answer a person can act on.

It fails closed. With no key, a failed call, or an answer that names a verdict
Datum did not return, the reply falls back to Datum's own advice, marked as
such. The model can explain a verdict; it can never change one.
"""
import json
import os
import re
import urllib.request

from .service import (PANEL, STALE_AFTER_HOURS, VERDICTS_ORDER, panel_path,
                      quote)
from .sources import hl_context

# Any OpenAI-compatible endpoint works. The default is the hackathon's Qwen
# endpoint; LLM_BASE_URL / LLM_MODEL / LLM_API_KEY point it elsewhere, for
# example OpenRouter's qwen/qwen3.8-flash, with no code change.
QWEN_BASE = (os.environ.get("LLM_BASE_URL") or os.environ.get("QWEN_BASE_URL")
             or "https://hackathon.bitgetops.com/v1")
QWEN_MODEL = (os.environ.get("LLM_MODEL") or os.environ.get("QWEN_MODEL")
              or "qwen3.8-max")
MAX_QUESTION = 400

# Company names a question is likely to use, for the tickers on the page.
NAMES = {
    "tesla": "TSLA", "nvidia": "NVDA", "apple": "AAPL", "microsoft": "MSFT",
    "google": "GOOGL", "alphabet": "GOOGL", "amazon": "AMZN", "meta": "META",
    "facebook": "META", "coinbase": "COIN", "robinhood": "HOOD",
    "palantir": "PLTR", "microstrategy": "MSTR", "circle": "CRCL",
    "gamestop": "GME", "broadcom": "AVGO",
}

SYSTEM = f"""You are Datum's analyst. Datum checks whether a tokenized US stock's price
can be trusted while the US cash market is closed, by comparing it with a validated
24/7 reference (the Hyperliquid equity perp) on two venues: Solana xStocks pools and
Bitget rTokens.

Rules:
- Answer only from FACTS. Quote figures exactly as given. Never invent a number.
- The verdicts in FACTS are final. Never contradict, soften or upgrade them.
  OK: the token price can be used. LAGGED: outside its expected band, price from the
  reference until it converges. STALE: no trade for over {STALE_AFTER_HOURS:.0f} hours, the
  token price is absent. NO_POOL / NO_REFERENCE: nothing to measure.
- Datum is a pricing check, not a trading signal. Never recommend a trade.
- If FACTS cannot answer the question, say what is missing.
- Plain English, at most 110 words, no headings, no bullet points.
- End with one line that starts "Action:" and says which price to use."""


def find_ticker(question: str, default: str | None, known: set[str]) -> str | None:
    words = re.findall(r"[A-Za-z]+", question)
    for w in words:
        u = w.upper()
        for cand in (u, u[:-1] if u.endswith("X") else None,
                     u[1:-4] if u.startswith("R") and u.endswith("USDT") else None,
                     u[1:] if u.startswith("R") else None):
            if cand and cand in known:
                return cand
        if w.lower() in NAMES:
            return NAMES[w.lower()]
    return default if default in known else None


def _panel_row(ticker: str, venue: str) -> dict | None:
    path = panel_path(venue)
    if not path.exists():
        return None
    for r in json.loads(path.read_text())["tickers"]:
        if r["ticker"] == ticker:
            return r
    return None


def facts(ticker: str) -> dict:
    """Everything the answer may use: live verdicts on both venues and the
    measured history behind each band."""
    contexts = hl_context()
    out = {"ticker": ticker, "stale_after_hours": STALE_AFTER_HOURS,
           "reference_validation": {"weekends": 21, "observations": 84,
                                    "retention": 1.048, "correlation": 0.855},
           "venues": {}}
    for venue in ("solana", "bitget"):
        try:
            q = quote(ticker, contexts, None, venue)
            live = {k: v for k, v in q.__dict__.items() if k != "venue"}
            for k in ("reference", "pool", "deviation_bps", "expected_bps",
                      "band_low", "band_high", "stale_hours"):
                if isinstance(live.get(k), float):
                    live[k] = round(live[k], 2)
        except Exception as exc:
            live = {"error": f"{type(exc).__name__}: {exc}"}
        row = _panel_row(ticker, venue)
        measured = None
        if row:
            measured = {
                "weekend_hours_measured": row["n"],
                "mean_abs_deviation_bps": round(row["mean_abs_dev_bps"], 1),
                "convergence_slope": {h + "h": round(c, 3) if c is not None else None
                                      for h, c in row["convergence"].items()},
                "median_weekend_volume_usd_per_hour": round(row["median_weekend_volume"]),
            }
        out["venues"][venue] = {"live": live, "measured_history": measured}
    return out


def _fallback(f: dict, reason: str) -> str:
    parts = []
    for venue, name in (("solana", "Solana xStocks"), ("bitget", "Bitget rTokens")):
        live = f["venues"][venue]["live"]
        if "verdict" in live:
            parts.append(f"{name}: {live['verdict']}. {live['advice']}")
        else:
            parts.append(f"{name}: no quote ({live.get('error', 'unavailable')}).")
    return " ".join(parts)


def _qwen(question: str, f: dict, key: str) -> str:
    body = {"model": QWEN_MODEL, "temperature": 0.2, "max_tokens": 400,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content":
                          "FACTS:\n" + json.dumps(f, indent=1) + "\n\nQUESTION: " + question}]}
    req = urllib.request.Request(
        QWEN_BASE.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                 # OpenRouter attributes traffic by these; other hosts ignore them
                 "HTTP-Referer": "https://datum-sandy.vercel.app", "X-Title": "Datum"})
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.load(r)
    return data["choices"][0]["message"]["content"].strip()


def _grounded(answer: str, f: dict) -> str | None:
    """Why an answer must be rejected, or None when it can stand."""
    returned = {v["live"].get("verdict") for v in f["venues"].values()} - {None}
    named = {v for v in VERDICTS_ORDER if re.search(rf"\b{v}\b", answer)}
    if named - returned:
        return "named a verdict Datum did not return: " + ", ".join(sorted(named - returned))
    if "Action:" not in answer:
        return "gave no action line"
    return None


def ask(question: str, ticker: str | None = None) -> dict:
    question = (question or "").strip()[:MAX_QUESTION]
    known = {r["ticker"] for r in json.loads(PANEL.read_text())["tickers"]}
    t = find_ticker(question, ticker, known)
    if not question:
        return {"error": "Ask a question, e.g. can I liquidate TSLA on Bitget right now?"}
    if not t:
        return {"error": "Name one of the tickers Datum measures: " + ", ".join(sorted(known))}
    f = facts(t)
    key = (os.environ.get("LLM_API_KEY") or os.environ.get("QWEN_API_KEY") or "").strip()
    reply = {"ticker": t, "question": question, "model": QWEN_MODEL, "facts": f}
    if not key:
        return {**reply, "answer": _fallback(f, "no key"), "llm": False,
                "reason": "Qwen is not configured on this server, so this is Datum's own advice."}
    try:
        answer = _qwen(question, f, key)
    except Exception as exc:
        return {**reply, "answer": _fallback(f, "call failed"), "llm": False,
                "reason": f"Qwen did not answer ({type(exc).__name__}), so this is "
                          "Datum's own advice."}
    why = _grounded(answer, f)
    if why:
        return {**reply, "answer": _fallback(f, why), "llm": False,
                "reason": f"Qwen's answer was withheld because it {why}. This is "
                          "Datum's own advice."}
    return {**reply, "answer": answer, "llm": True}
