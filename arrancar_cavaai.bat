@echo off
REM CavaAI - arranque en 1 click: infra + backend + frontend + navegador
cd /d "%~dp0"
echo [1/4] Levantando Docker (postgres, qdrant, minio, redis)...
docker compose up -d --no-build
echo [2/4] Esperando a Qdrant...
for /L %%i in (1,1,30) do (
  curl -sf http://localhost:6333/healthz >nul 2>&1 && goto qdrant_ok
  timeout /t 2 /nobreak >nul
)
echo AVISO: Qdrant no responde; sigo sin busqueda semantica.
:qdrant_ok
echo [3/4] Migraciones de base de datos...
cd data-engine
.\.venv\Scripts\python.exe -m alembic upgrade head
start "CavaAI backend" .\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
cd ..
echo [4/4] Frontend...
start "CavaAI frontend" node_modules\.bin\next dev -p 3000
echo Esperando al frontend (primera vez compila ~1 min)...
for /L %%i in (1,1,30) do (
  curl -sf http://localhost:3000/ >nul 2>&1 && goto web_ok
  timeout /t 4 /nobreak >nul
)
:web_ok
start http://localhost:3000/
echo Listo: http://localhost:3000/
pause
