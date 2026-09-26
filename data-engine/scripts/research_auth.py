"""Firma estricta (ligada al request) para los scripts e2e locales.

Replica el payload endurecido de app.core.auth: la firma cubre
tenant:user:timestamp:nonce:METHOD:path:sha256(body), con nonce de un solo
uso. Funciona tanto contra un backend leniente (legacy permitido) como contra
uno estricto (research_auth_strict_binding=True), porque la firma ligada se
acepta en ambos modos.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from uuid import uuid4


def load_secret(env_path: str = ".env") -> str:
    with open(env_path, encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("RESEARCH_AUTH_SECRET="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(f"RESEARCH_AUTH_SECRET no encontrado en {env_path}")


def signed_headers(
    secret: str,
    tenant: str,
    user: str,
    *,
    method: str,
    path: str,
    body: bytes = b"",
) -> dict[str, str]:
    """Cabeceras X-CavaAI-* con firma ligada a metodo, ruta y cuerpo.

    `path` debe ser solo la ruta (sin query string): el servidor verifica
    contra request.url.path.
    """
    timestamp = str(int(time.time()))
    nonce = uuid4().hex
    body_hash = hashlib.sha256(body).hexdigest()
    payload = f"{tenant}:{user}:{timestamp}:{nonce}:{method.upper()}:{path}:{body_hash}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {
        "X-CavaAI-User": user,
        "X-CavaAI-Tenant": tenant,
        "X-CavaAI-Timestamp": timestamp,
        "X-CavaAI-Nonce": nonce,
        "X-CavaAI-Method": method.upper(),
        "X-CavaAI-Path": path,
        "X-CavaAI-Body-Hash": body_hash,
        "X-CavaAI-Signature": signature,
    }
