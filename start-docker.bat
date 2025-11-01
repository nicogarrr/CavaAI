@echo off
echo ========================================
echo   Iniciando MongoDB con Docker
echo ========================================
echo.

echo Verificando Docker...
docker --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker no esta instalado o no esta corriendo.
    echo.
    echo Por favor:
    echo 1. Instala Docker Desktop desde: https://www.docker.com/products/docker-desktop
    echo 2. Inicia Docker Desktop
    echo 3. Ejecuta este script nuevamente
    echo.
    pause
    exit /b 1
)

echo Docker encontrado!
echo.
echo Iniciando MongoDB...
docker compose up -d mongodb

if errorlevel 1 (
    echo.
    echo ERROR: No se pudo iniciar MongoDB.
    echo Verifica que Docker Desktop este corriendo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   MongoDB iniciado correctamente!
echo ========================================
echo.
echo Puedes conectarte en: localhost:27017
echo Usuario: root
echo Password: example
echo.
echo Presiona cualquier tecla para cerrar...
pause >nul

