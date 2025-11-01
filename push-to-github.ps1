# Script para hacer push a GitHub
# Instrucciones:
# 1. Ve a https://github.com/settings/tokens
# 2. Genera un token con permisos "repo"
# 3. Ejecuta este script y pega el token cuando te lo pida

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Push a GitHub - OpenStock" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$token = Read-Host "Ingresa tu Personal Access Token de GitHub"

if ([string]::IsNullOrWhiteSpace($token)) {
    Write-Host "Error: El token no puede estar vacío" -ForegroundColor Red
    exit 1
}

# Configurar remote con token
git remote set-url origin "https://$token@github.com/Open-Dev-Society/OpenStock.git"

Write-Host ""
Write-Host "Intentando hacer push..." -ForegroundColor Yellow

# Hacer push
$result = git push origin main 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ Push exitoso!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Ahora puedes desplegar en Vercel:" -ForegroundColor Cyan
    Write-Host "1. Ve a https://vercel.com" -ForegroundColor White
    Write-Host "2. Conecta tu repositorio GitHub" -ForegroundColor White
    Write-Host "3. Configura las variables de entorno" -ForegroundColor White
    Write-Host "4. Despliega!" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "❌ Error en el push:" -ForegroundColor Red
    Write-Host $result -ForegroundColor Red
    Write-Host ""
    Write-Host "Soluciones posibles:" -ForegroundColor Yellow
    Write-Host "1. Verifica que el token tenga permisos 'repo'" -ForegroundColor White
    Write-Host "2. Verifica que tengas acceso al repositorio Open-Dev-Society/OpenStock" -ForegroundColor White
    Write-Host "3. Intenta generar un nuevo token" -ForegroundColor White
}

# Restaurar remote original (sin token en la URL)
git remote set-url origin "https://github.com/Open-Dev-Society/OpenStock.git"

Write-Host ""
Write-Host "Nota: El token fue removido del remote por seguridad" -ForegroundColor Gray

