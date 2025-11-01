@echo off
echo ========================================
echo   OpenStock - Iniciando Aplicacion
echo ========================================
echo.

echo Verificando dependencias...
if not exist "node_modules\" (
    echo Instalando dependencias...
    call npm install
    echo.
)

echo.
echo ========================================
echo   Iniciando Next.js Dev Server
echo ========================================
echo.
echo La aplicacion estara disponible en:
echo http://localhost:3000
echo.
echo Para detener el servidor, presiona Ctrl+C
echo.
echo NOTA: Si tienes errores de conexion a MongoDB,
echo sigue las instrucciones en INSTRUCCIONES_DESPLIEGUE.md
echo para configurar MongoDB Atlas (gratis)
echo.

call npm run dev

