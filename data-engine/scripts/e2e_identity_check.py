import urllib.error
import urllib.request

from research_auth import load_secret, signed_headers

secret = load_secret()
TENANT = USER = "e2e-check-user"


def call(path: str):
    headers = signed_headers(secret, TENANT, USER, method="GET", path=path)
    req = urllib.request.Request("http://127.0.0.1:8000" + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:140]
        return f"HTTP {e.code}: {body}"


print("/api/companies ->", call("/api/companies"))
print("/api/settings   ->", call("/api/settings"))
print("/quote/AAPL     ->", call("/quote/AAPL"))
