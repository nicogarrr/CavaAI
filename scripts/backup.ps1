param(
    [string]$BackupRoot = (Join-Path $PSScriptRoot "..\backups"),
    [switch]$IncludeStorageVolumes
)

$ErrorActionPreference = "Stop"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$root = [System.IO.Path]::GetFullPath($BackupRoot)
$destination = Join-Path $root $stamp
New-Item -ItemType Directory -Path $destination -Force | Out-Null

$postgres = (docker compose ps -q postgres).Trim()
if (-not $postgres) { throw "The postgres compose service is not running." }
docker exec $postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/cavaai.dump'
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed." }
docker cp "${postgres}:/tmp/cavaai.dump" (Join-Path $destination "postgres.dump")
docker exec $postgres rm -f /tmp/cavaai.dump

if ($IncludeStorageVolumes) {
    $services = @("mongodb", "qdrant", "minio")
    docker compose stop @services
    try {
        $volumes = @(
            @{ Name = "cavaai-mongodb-data"; File = "mongodb.tar.gz" },
            @{ Name = "cavaai-qdrant-data"; File = "qdrant.tar.gz" },
            @{ Name = "cavaai-minio-data"; File = "minio.tar.gz" }
        )
        foreach ($item in $volumes) {
            docker run --rm `
                --mount "type=volume,source=$($item.Name),target=/source,readonly" `
                --mount "type=bind,source=$destination,target=/backup" `
                alpine:3.20 tar -C /source -czf "/backup/$($item.File)" .
            if ($LASTEXITCODE -ne 0) { throw "Backup failed for $($item.Name)." }
        }
    }
    finally {
        docker compose start @services
    }
}

$manifest = @{
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    postgres = "postgres.dump"
    storage_volumes = [bool]$IncludeStorageVolumes
    compose_project = "CavaAI"
} | ConvertTo-Json
Set-Content -LiteralPath (Join-Path $destination "manifest.json") -Value $manifest -Encoding utf8
Write-Output "Backup completed: $destination"
