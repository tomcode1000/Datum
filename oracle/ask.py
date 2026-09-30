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

from .service import (PANEL, STALE_AFTER_HOURS, VENUES, VERDICTS_ORDER,
                      panel_path, quote, sweep_json)
from .sources import hl_context

# Any OpenAI-compatible endpoint works. The default is the hackathon's Qwen
# endpoint; LLM_BASE_URL / LLM_MODEL / LLM_API_KEY point it elsewhere, for
# example OpenRouter's qwen/qwen3.8-flash, with no code change.
QWEN_BASE = (os.environ.get("LLM_BASE_URL") or os.environ.get("QWEN_BASE_URL")
             or "https://hackathon.bitgetops.com/v1")
QWEN_MODEL = (os.environ.get("LLM_MODEL") or os.environ.get("QWEN_MODEL")
              or "qwen3.8-max")
MAX_QUESTION = 400
MAX_POSITIONS = 10
MAX_TURNS = 3

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
- Valuing collateral, liquidating a position and marking a book are exactly what
  Datum is for: answer them directly with which price is safe to use. Only advice
  to buy or sell for profit is out of scope; Datum is a pricing check, not a
  trading signal.
- Questions about now use each venue's live quote. Questions about weekends,
  history or which venue is usually closer use the measured weekend history, and
  the "comparison" block states the result: report it, do not recompute it. Say
  whether you are using the live quotes or the measured weekend history.
- Live quotes carry "session": the US cash market is open, overnight or in the
  weekend gap. Mention it when it matters.
- Name only the verdicts Datum returned in FACTS. Never name another verdict,
  not even to say it does not apply ("not STALE" is not allowed; say "traded
  within the hour" instead).
- Never mention FACTS, the comparison block or any field name; just state the
  finding.
- Write figures as a person would ("2.6 bps below the reference", "$350.66",
  "traded within the hour"), never as field names.
- If FACTS cannot answer the question, say what is missing.
- Plain English, at most 110 words, no headings, no bullet points.
- If FACTS include "your_positions", these are the user's own holdings: answer
  for them. For each, say the price to mark it at, its value there, and how far
  it is from its liquidation price. If "token_price_alone_would_liquidate" is
  true for any, say so first: the drifted token price would trigger a
  liquidation the trusted price would not.
- Earlier questions and answers may come first. Answer the latest question from
  the latest FACTS; earlier figures may be out of date.
- End with one line that starts "Action:" and says which price to use right
  now, following the live verdicts: a venue marked OK can be priced from; for
  LAGGED or STALE, use the reference."""


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
    out["comparison"] = _compare(out["venues"])
    return out


def _compare(venues: dict) -> dict:
    """Venue comparisons computed here, so the model reports them rather than
    reading negative slopes itself (it got one backwards in testing)."""
    h = {v: d["measured_history"] for v, d in venues.items() if d["measured_history"]}
    out = {}
    if len(h) == 2:
        s, b = h["solana"], h["bitget"]
        out["closer_to_reference_on_average_at_weekends"] = (
            "solana" if s["mean_abs_deviation_bps"] < b["mean_abs_deviation_bps"] else "bitget")
        for k in ("1h", "12h"):
            cs, cb = s["convergence_slope"].get(k), b["convergence_slope"].get(k)
            if cs is not None and cb is not None:
                out[f"corrects_faster_{k}"] = "solana" if cs < cb else "bitget"
    live = {v: d["live"] for v, d in venues.items() if d["live"].get("deviation_bps") is not None}
    if len(live) == 2:
        out["closer_to_reference_right_now"] = min(
            live, key=lambda v: abs(live[v]["deviation_bps"]))
    return out


def _positions(raw, known: set[str]) -> list[dict]:
    """The user's holdings, validated, each marked at the price Datum trusts."""
    clean = []
    for p in (raw or [])[:MAX_POSITIONS]:
        try:
            t = str(p.get("ticker", "")).upper().strip()
            venue = str(p.get("venue", "bitget")).lower()
            qty = float(p.get("quantity"))
            liq = p.get("liquidation_price")
            liq = float(liq) if liq not in (None, "") else None
        except (TypeError, ValueError, AttributeError):
            continue
        if t in known and venue in VENUES and 0 < qty <= 1e9 and (liq is None or liq > 0):
            clean.append({"ticker": t, "venue": venue, "quantity": qty,
                          "liquidation_price": liq})
    if not clean:
        return []
    sweeps = {v: {q["ticker"]: q for q in json.loads(sweep_json(v))["quotes"] if "ticker" in q}
              for v in {p["venue"] for p in clean}}
    out = []
    for p in clean:
        q = sweeps[p["venue"]].get(p["ticker"], {})
        verdict, token, ref = q.get("verdict"), q.get("pool"), q.get("reference")
        # OK: the token price stands. Otherwise the reference is the price to use.
        trusted = token if verdict == "OK" else ref
        row = {**p, "verdict": verdict, "token_price": token, "reference_price": ref,
               "mark_at": "token price" if verdict == "OK" else "reference",
               "trusted_price": trusted}
        if trusted:
            row["value_at_trusted_price"] = round(p["quantity"] * trusted, 2)
        if token:
            row["value_at_token_price"] = round(p["quantity"] * token, 2)
        liq = p["liquidation_price"]
        if liq and trusted:
            row["distance_to_liquidation_pct"] = round((trusted - liq) / trusted * 100, 2)
            row["token_price_alone_would_liquidate"] = bool(token and token <= liq < trusted)
        out.append(row)
    return out


def _fallback(f: dict, reason: str) -> str:
    parts = []
    for venue, name in (("solana", "Solana xStocks"), ("bitget", "Bitget rTokens")):
        live = f["venues"][venue]["live"]
        if "verdict" in live:
            parts.append(f"{name}: {live['verdict']}. {live['advice']}")
        else:
            parts.append(f"{name}: no quote ({live.get('error', 'unavailable')}).")
    for p in f.get("your_positions", []):
        if p.get("trusted_price"):
            line = (f"Your {p['quantity']:g} {p['ticker']} on {p['venue']}: mark at the "
                    f"{p['mark_at']}, {p['trusted_price']:.2f}")
            if p.get("distance_to_liquidation_pct") is not None:
                line += f", {p['distance_to_liquidation_pct']:.1f}% above its liquidation price"
            if p.get("token_price_alone_would_liquidate"):
                line += ". The token price alone would liquidate it; the trusted price does not"
            parts.append(line + ".")
    return " ".join(parts)


def _qwen(question: str, f: dict, key: str, history: list[dict] | None = None) -> str:
    messages = [{"role": "system", "content": SYSTEM}]
    for turn in (history or [])[-MAX_TURNS:]:
        q, a = str(turn.get("q", ""))[:MAX_QUESTION], str(turn.get("a", ""))[:1500]
        if q and a:
            messages += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    messages.append({"role": "user", "content":
                     "FACTS:\n" + json.dumps(f, indent=1) + "\n\nQUESTION: " + question})
    body = {"model": QWEN_MODEL, "temperature": 0.2, "max_tokens": 900, "messages": messages}
    if "openrouter.ai" in QWEN_BASE:
        # Qwen 3.8 reasons before it answers, and on Datum's facts that spent the
        # whole token budget with no answer left. The verdict is already decided;
        # the model only has to explain it, so reasoning is switched off.
        body["reasoning"] = {"enabled": False}
    req = urllib.request.Request(
        QWEN_BASE.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                 # OpenRouter attributes traffic by these; other hosts ignore them
                 "HTTP-Referer": "https://datum-sandy.vercel.app", "X-Title": "Datum"})
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.load(r)
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
    if not content or not content.strip():
        raise ValueError("the model returned no answer")
    return content.strip()


def _grounded(answer: str, f: dict) -> str | None:
    """Why an answer must be rejected, or None when it can stand."""
    returned = ({v["live"].get("verdict") for v in f["venues"].values()}
                | {p.get("verdict") for p in f.get("your_positions", [])}) - {None}
    # Case-insensitive and tolerant of spacing ("lagged", "No Pool"); OK stays
    # exact, since "ok" is an ordinary word.
    named = set()
    for v in VERDICTS_ORDER:
        if v == "OK":
            hit = re.search(r"\bOK\b", answer)
        else:
            hit = re.search(r"\b" + v.replace("_", r"[\s_-]?") + r"\b", answer, re.IGNORECASE)
        if hit:
            named.add(v)
    if named - returned:
        return "named a verdict Datum did not return: " + ", ".join(sorted(named - returned))
    if "Action:" not in answer:
        return "gave no action line"
    return None


def ask(question: str, ticker: str | None = None, positions: list | None = None,
        history: list | None = None) -> dict:
    question = (question or "").strip()[:MAX_QUESTION]
    known = {r["ticker"] for r in json.loads(PANEL.read_text())["tickers"]}
    if not question:
        return {"error": "Ask a question, e.g. can I liquidate TSLA on Bitget right now?"}
    try:
        mine = _positions(positions, known)
    except Exception:
        mine = []            # positions are context; a failure must not block the answer
    # a question that names no ticker is about the last one discussed, or your positions
    t = find_ticker(question, ticker or (mine[0]["ticker"] if mine else None), known)
    if not t:
        return {"error": "Name one of the tickers Datum measures: " + ", ".join(sorted(known))}
    f = facts(t)
    if mine:
        f["your_positions"] = mine
    key = (os.environ.get("LLM_API_KEY") or os.environ.get("QWEN_API_KEY") or "").strip()
    reply = {"ticker": t, "question": question, "model": QWEN_MODEL, "facts": f}
    if not key:
        return {**reply, "answer": _fallback(f, "no key"), "llm": False,
                "reason": "Qwen is not configured on this server, so this is Datum's own advice."}
    try:
        answer = _qwen(question, f, key, history if isinstance(history, list) else None)
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
