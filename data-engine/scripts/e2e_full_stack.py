import hashlib
import hmac
import io
import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
secret = [l.split("=", 1)[1].strip() for l in open(".env", encoding="utf-8") if l.startswith("RESEARCH_AUTH_SECRET=")][0]
TENANT = USER = "e2e-full-stack"


def headers():
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), f"{TENANT}:{USER}:{ts}".encode(), hashlib.sha256).hexdigest()
    return {
        "X-CavaAI-User": USER,
        "X-CavaAI-Tenant": TENANT,
        "X-CavaAI-Timestamp": ts,
        "X-CavaAI-Signature": sig,
    }


def request(path, method="GET", body=None, raw=None, content_type=None, timeout=120):
    h = headers()
    data = None
    if raw is not None:
        data = raw
        h["Content-Type"] = content_type
    elif body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(payload) if payload else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:400]


doc_text = (
    "Rocket Lab Q2 2026 Shareholder Letter (synthetic e2e fixture).\n"
    "Neutron development is on track for a first test flight in 2027.\n"
    "Backlog reached 1.1 billion USD with a growing defense mix.\n"
    "Launch cadence averaged 5 Electron missions per quarter.\n"
    "Gross margin improved to 27 percent on space systems strength.\n"
)

boundary = "----cavaai-e2e-boundary"
parts = [
    f'--{boundary}\r\nContent-Disposition: form-data; name="ticker"\r\n\r\nRKLB\r\n',
    f'--{boundary}\r\nContent-Disposition: form-data; name="title"\r\n\r\ne2e-vector-fixture-letter\r\n',
    f'--{boundary}\r\nContent-Disposition: form-data; name="source_type"\r\n\r\nmanual_upload\r\n',
    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="letter.txt"\r\n'
    f'Content-Type: text/plain\r\n\r\n{doc_text}\r\n',
    f"--{boundary}--\r\n",
]

body_bytes = "".join(parts).encode()

print("1) ingest-file:", request(
    "/api/sources/documents/ingest-file",
    method="POST",
    raw=body_bytes,
    content_type=f"multipart/form-data; boundary={boundary}",
))

time.sleep(3)
status, docs = request("/api/sources/documents?ticker=RKLB&limit=3")
print("2) documents:", status, json.dumps(docs, ensure_ascii=False)[:300])

print("3) vector chat:", request(
    "/api/chat",
    method="POST",
    body={"question": "What does the Rocket Lab letter say about Neutron timing and backlog?", "scope": "company", "ticker": "RKLB"},
))
