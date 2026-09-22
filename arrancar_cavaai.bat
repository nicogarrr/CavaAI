@echo off
REM =====================================================================
REM CavaAI - arranque en 1 click: infra + backend + frontend + navegador
REM =====================================================================
REM MODOS (primer parametro):
REM   arrancar_cavaai.bat          DEV por defecto:  `next dev -p 3000`
REM   arrancar_cavaai.bat /prod    PROD: `next build` una vez + `next start -p 3000`
REM   (tambien valen: prod, --prod, -prod)
REM ---------------------------------------------------------------------
REM QUE MODO USAR:
REM   - DEV (diario / programar): arranque rapido, compila cada pagina
REM     bajo demanda (~1 min la primera vez que abres cada pagina).
REM     Usa este modo salvo que necesites lo de abajo.
REM   - PROD (/prod): valida el modo produccion local. Hace `next build`
REM     una vez (~2 min 20 s medido 2026-09-21) y luego sirve con
REM     `next start`: navegacion mas rapida, errores de build reales
REM     (los que veria el despliegue). Usalo antes de desplegar o para
REM     probar rendimiento. Si el build falla, el .bat se detiene y NO
REM     arranca el frontend.
REM =====================================================================
cd /d "%~dp0"
set "FRONT_MODE=DEV"
if /i "%~1"=="/prod" set "FRONT_MODE=PROD"
if /i "%~1"=="prod" set "FRONT_MODE=PROD"
if /i "%~1"=="--prod" set "FRONT_MODE=PROD"
if /i "%~1"=="-prod" set "FRONT_MODE=PROD"
echo CavaAI - modo %FRONT_MODE%
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
if /i "%FRONT_MODE%"=="PROD" goto frontend_prod
:frontend_dev
echo [4/4] Frontend DEV (next dev)...
start "CavaAI frontend" node_modules\.bin\next dev -p 3000
echo Esperando al frontend (primera vez compila ~1 min)...
goto wait_web
:frontend_prod
echo [4/4] Frontend PROD: build una vez (~2 min) + next start...
call node_modules\.bin\next build
if errorlevel 1 (
  echo ERROR: `next build` fallo; revisa los errores de arriba. Frontend NO arrancado.
  pause
  exit /b 1
)
start "CavaAI frontend (prod)" node_modules\.bin\next start -p 3000
echo Esperando al frontend prod (arranca en ~2 s tras el build)...
:wait_web
for /L %%i in (1,1,30) do (
  curl -sf http://localhost:3000/ >nul 2>&1 && goto web_ok
  timeout /t 4 /nobreak >nul
)
:web_ok
start http://localhost:3000/
echo Listo (%FRONT_MODE%): http://localhost:3000/
pause
