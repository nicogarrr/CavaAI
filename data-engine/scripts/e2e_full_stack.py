import json
import time
import urllib.error
import urllib.request

from research_auth import load_secret, signed_headers

BASE = "http://127.0.0.1:8000"
secret = load_secret()
TENANT = USER = "e2e-full-stack"


def request(path, method="GET", body=None, raw=None, content_type=None, timeout=120):
    data = None
    extra = {}
    if raw is not None:
        data = raw
        extra["Content-Type"] = content_type
    elif body is not None:
        data = json.dumps(body).encode()
        extra["Content-Type"] = "application/json"
    headers = signed_headers(
        secret, TENANT, USER, method=method, path=path.split("?", 1)[0], body=data or b""
    )
    headers.update(extra)
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
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
