import hashlib
import hmac
import time
import urllib.error
import urllib.request

secret = [l.split("=", 1)[1].strip() for l in open(".env", encoding="utf-8") if l.startswith("RESEARCH_AUTH_SECRET=")][0]
print("secret repr tail:", repr(secret[-6:]))


def call(path: str):
    tenant = user = "e2e-check-user"
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), f"{tenant}:{user}:{ts}".encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        "http://127.0.0.1:8000" + path,
        headers={
            "X-CavaAI-User": user,
            "X-CavaAI-Tenant": tenant,
            "X-CavaAI-Timestamp": ts,
            "X-CavaAI-Signature": sig,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:140]
        return f"HTTP {e.code}: {body}"


print("/api/companies ->", call("/api/companies"))
print("/api/settings   ->", call("/api/settings"))
print("/quote/AAPL     ->", call("/quote/AAPL"))
