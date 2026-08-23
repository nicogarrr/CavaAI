import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8000"
secret = [l.split("=", 1)[1].strip() for l in open(".env", encoding="utf-8") if l.startswith("RESEARCH_AUTH_SECRET=")][0]
TENANT = USER = "e2e-finance-modules"


def headers():
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), f"{TENANT}:{USER}:{ts}".encode(), hashlib.sha256).hexdigest()
    return {
        "X-CavaAI-User": USER,
        "X-CavaAI-Tenant": TENANT,
        "X-CavaAI-Timestamp": ts,
        "X-CavaAI-Signature": sig,
    }


def request(path, method="GET", body=None, timeout=60):
    h = headers()
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read().decode("utf-8", "replace")
            if path.endswith("format=csv"):
                return r.status, payload[:300]
            return r.status, (json.loads(payload) if payload else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]


def show(label, result):
    status, payload = result
    text = json.dumps(payload, ensure_ascii=False) if not isinstance(payload, str) else payload
    print(f"{label}: {status} | {text[:600]}")


show("plan GET (empty)     ", request("/api/plan"))
show("plan PUT (crear)     ", request("/api/plan", "PUT", {
    "monthly_contribution": 1500,
    "start_date": "2026-01-01",
    "horizon_years": 30,
    "target_allocations": [
        {"kind": "sector", "label": "Technology", "target_pct": 30, "band_pct": 5},
        {"kind": "sector", "label": "Industrials", "target_pct": 20, "band_pct": 5},
        {"kind": "asset_class", "label": "Cash", "target_pct": 10, "band_pct": 5},
    ],
}))
show("contribution POST    ", request("/api/plan/contributions", "POST", {
    "date": "2026-01-15", "amount": 1500, "currency": "EUR", "note": "enero 2026"
}))
show("plan GET (con plan)  ", request("/api/plan"))
show("plan drift           ", request("/api/plan/drift"))
show("tax report 2026      ", request("/api/taxes/report/2026"))
show("corporate-actions GET", request("/api/corporate-actions"))

# Seed a company + transactions to exercise FIFO tax math
show("seed transaction     ", request("/api/portfolio/transactions", "POST", {
    "ticker": "RKLB", "action": "buy", "quantity": 100, "price": 20,
    "trade_date": "2025-06-01", "currency": "USD", "fees": 1,
}))
show("seed transaction 2   ", request("/api/portfolio/transactions", "POST", {
    "ticker": "RKLB", "action": "buy", "quantity": 50, "price": 30,
    "trade_date": "2026-02-01", "currency": "USD", "fees": 1,
}))
show("seed sell            ", request("/api/portfolio/transactions", "POST", {
    "ticker": "RKLB", "action": "sell", "quantity": 40, "price": 35,
    "trade_date": "2026-05-15", "currency": "USD", "fees": 1,
}))
show("seed dividend        ", request("/api/portfolio/transactions", "POST", {
    "ticker": "RKLB", "action": "dividend", "quantity": 0, "price": 12.5,
    "trade_date": "2026-06-10", "currency": "USD", "fees": 0,
}))
show("tax report 2026 v2   ", request("/api/taxes/report/2026", "GET", None))
show("tax regenerate       ", request("/api/taxes/report/2026/regenerate", "POST", None))
show("export 2026 csv head ", request("/api/export/2026?format=csv"))
show("export 2026 json     ", request("/api/export/2026?format=json"))

# Corporate action: 1:4 split on RKLB after buys
show("split create         ", request("/api/corporate-actions", "POST", {
    "ticker": "RKLB", "action_type": "split", "effective_date": "2026-07-01",
    "ratio": 4, "description": "e2e 1:4 split",
}))
show("split list           ", request("/api/corporate-actions"))