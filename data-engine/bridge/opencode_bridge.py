"""Puente OpenAI-compatible -> opencode serve (session/message API).

Por que existe: el free tier de Zen solo responde desde un cliente OpenCode
real. Este puente recibe POST /v1/chat/completions (OpenAI shape) del
data-engine y lo traduce al flujo de sesiones del serve enjaulado
(oc-serve2), de modo que los modelos free (deepseek-v4.1-flash-free,
space-bunny-free) funcionan a coste 0 desde CavaAI.

Limites declarados:
- Sin streaming (devuelve la respuesta completa; ignora "stream").
- Sin tools/function calling: si llega "tools" en el payload responde 400
  (fallo visible, nunca ejecucion simulada).
- response_format json_schema se traduce a instruccion de prompt.
- Sin auth propia: solo escucha en la red interna de docker.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVE_URL = os.environ.get("SERVE_URL", "http://oc-serve2:4096").rstrip("/")
PROVIDER_ID = os.environ.get("PROVIDER_ID", "opencode")
POLL_S = float(os.environ.get("POLL_S", "2"))
TIMEOUT_S = float(os.environ.get("TIMEOUT_S", "30"))
REQUEST_TIMEOUT_S = float(os.environ.get("REQUEST_TIMEOUT_S", "10"))
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "4098"))


def serve_req(method: str, path: str, body=None, timeout=None):
    req = urllib.request.Request(
        SERVE_URL + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout or REQUEST_TIMEOUT_S) as res:
        raw = res.read()
        return json.loads(raw) if raw else None


def flatten_messages(messages) -> str:
    out = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):  # partes multimodales: solo texto
            content = " ".join(p.get("text", "") for p in content
                               if isinstance(p, dict) and p.get("type") == "text")
        out.append(f"[{role}]\n{content}")
    return "\n\n".join(out)


class ProviderRateLimitError(RuntimeError):
    pass


def complete(model: str, messages, response_format=None, reasoning_effort=None) -> str:
    prompt = flatten_messages(messages)
    if response_format and isinstance(response_format, dict):
        js = response_format.get("json_schema") or {}
        schema = js.get("schema")
        if schema:
            prompt += ("\n\nResponde SOLO con JSON valido que cumpla este "
                       "esquema, sin texto extra ni markdown:\n"
                       + json.dumps(schema, ensure_ascii=False))
    sid = serve_req("POST", "/session", {"title": "CavaAI chat"})["id"]
    t0 = time.monotonic()
    try:
        msg = {"model": {"providerID": PROVIDER_ID, "modelID": model},
               "parts": [{"type": "text", "text": prompt}]}
        if reasoning_effort:
            # variants del serve (verificado 2026-10-16: deepseek-v4.1-flash-free
            # tiene low|high|max; space-bunny-free low|medium|high|xhigh|max)
            msg["variant"] = reasoning_effort
            print(f"bridge: {model} variant={reasoning_effort}", flush=True)
        serve_req("POST", f"/session/{sid}/prompt_async", msg)
        while time.monotonic() - t0 < TIMEOUT_S:
            statuses = serve_req("GET", "/session/status") or {}
            status = statuses.get(sid, {})
            if status.get("type") == "retry":
                message = str(status.get("message", ""))
                if any(marker in message.lower() for marker in ("rate limit", "quota", "429", "free tier")):
                    raise ProviderRateLimitError("El proveedor gratuito ha limitado las solicitudes; inténtalo más tarde.")
            textos = []
            for m in serve_req("GET", f"/session/{sid}/message"):
                info = m.get("info", {})
                if info.get("role") != "assistant":
                    continue
                for p in m.get("parts", []):
                    if p.get("type") == "text" and p.get("text"):
                        textos.append(p["text"])
                if info.get("error"):
                    raise RuntimeError("serve error: " + json.dumps(info["error"])[:300])
                if info.get("finish") and info.get("finish") != "tool-calls":
                    return " ".join(textos).strip()
            time.sleep(POLL_S)
        raise TimeoutError(f"serve no termino en {TIMEOUT_S}s")
    finally:
        for method, path in (("POST", f"/session/{sid}/abort"), ("DELETE", f"/session/{sid}")):
            try:
                serve_req(method, path, {} if method == "POST" else None, timeout=2)
            except Exception:
                pass


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("bridge:", fmt % args, flush=True)

    def _send_json(self, code: int, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"ok": True})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._send_json(404, {"error": "not found"})
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        except Exception:
            self._send_json(400, {"error": "invalid json"})
            return
        if body.get("tools"):
            self._send_json(400, {"error": {"type": "UnsupportedError",
                "message": "bridge no soporta tools/function calling"}})
            return
        model = body.get("model", "")
        messages = body.get("messages", [])
        if not model or not messages:
            self._send_json(400, {"error": "model y messages requeridos"})
            return
        try:
            text = complete(model, messages, body.get("response_format"),
                            body.get("reasoning_effort"))
        except Exception as e:
            self._send_json(429 if isinstance(e, ProviderRateLimitError) else 502, {"type": "error", "error": {
                "type": type(e).__name__, "message": str(e)[:400]}})
            return
        self._send_json(200, {
            "id": "chatcmpl-bridge", "object": "chat.completion",
            "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}})


if __name__ == "__main__":
    print(f"bridge escuchando :{LISTEN_PORT} -> {SERVE_URL}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler).serve_forever()
