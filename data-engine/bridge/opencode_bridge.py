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
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVE_URL = os.environ.get("SERVE_URL", "http://oc-serve2:4096").rstrip("/")
PROVIDER_ID = os.environ.get("PROVIDER_ID", "opencode")
POLL_S = float(os.environ.get("POLL_S", "2"))
TIMEOUT_S = float(os.environ.get("TIMEOUT_S", "150"))
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "4098"))


def serve_req(method: str, path: str, body=None):
    req = urllib.request.Request(
        SERVE_URL + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.load(res)


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


def complete(model: str, messages, response_format=None) -> str:
    prompt = flatten_messages(messages)
    if response_format and isinstance(response_format, dict):
        js = response_format.get("json_schema") or {}
        schema = js.get("schema")
        if schema:
            prompt += ("\n\nResponde SOLO con JSON valido que cumpla este "
                       "esquema, sin texto extra ni markdown:\n"
                       + json.dumps(schema, ensure_ascii=False))
    sid = serve_req("POST", "/session", {})["id"]
    t0 = time.time()
    try:
        serve_req("POST", f"/session/{sid}/message", {
            "model": {"providerID": PROVIDER_ID, "modelID": model},
            "parts": [{"type": "text", "text": prompt}]})
        textos = []
        while time.time() - t0 < TIMEOUT_S:
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
        try:
            serve_req("DELETE", f"/session/{sid}")
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
            text = complete(model, messages, body.get("response_format"))
        except Exception as e:
            self._send_json(502, {"type": "error", "error": {
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
