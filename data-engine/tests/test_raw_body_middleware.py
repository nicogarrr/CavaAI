"""Regresion F12: RawBodyMiddleware no debe abortar respuestas en streaming.

El receive de replay devolvia un "http.disconnect" fabricado en la segunda
llamada; StreamingResponse lo interpreta como cliente colgado y cancela el
cuerpo: 200 con 0 bytes (rompia /api/export y las descargas de tesis).
"""

import io

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from app.core.raw_body import RawBodyMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RawBodyMiddleware)

    @app.get("/stream")
    def stream():
        return StreamingResponse(io.BytesIO(b"type,date\r\nt,2026-01-01\r\n"), media_type="text/csv")

    @app.post("/echo")
    async def echo(request: Request):
        body = await request.body()
        return JSONResponse({"len": len(body)})

    return app


def test_streaming_response_survives_raw_body_middleware():
    client = TestClient(_app())
    response = client.get("/stream")
    assert response.status_code == 200
    assert response.content == b"type,date\r\nt,2026-01-01\r\n"


def test_request_body_still_replays():
    client = TestClient(_app())
    response = client.post("/echo", content=b"payload-bytes")
    assert response.status_code == 200
    assert response.json() == {"len": len(b"payload-bytes")}
