param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$mappings = [ordered]@{
    "jlcava-postgres-data" = "cavaai-postgres-data"
    "jlcava-mongodb-data" = "cavaai-mongodb-data"
    "jlcava-minio-data" = "cavaai-minio-data"
    "jlcava-qdrant-data" = "cavaai-qdrant-data"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI is required."
}

$running = docker ps --format "{{.Names}}" | Where-Object {
    $_ -like "cavaai-*" -or $_ -like "jlcava-*"
}
if ($running) {
    throw "Stop CavaAI containers before migrating volumes: $($running -join ', ')"
}

foreach ($entry in $mappings.GetEnumerator()) {
    $source = $entry.Key
    $target = $entry.Value
    docker volume inspect $source *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Skip $source (source volume does not exist)."
        continue
    }

    Write-Host "$source -> $target"
    if ($DryRun) {
        continue
    }

    docker volume create $target *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create target volume $target."
    }

    docker run --rm -v "${target}:/target" alpine:3.20 sh -c "test -z \"`$(ls -A /target)\""
    if ($LASTEXITCODE -ne 0) {
        throw "Target volume $target is not empty; refusing to overwrite it."
    }

    docker run --rm -v "${source}:/source:ro" -v "${target}:/target" alpine:3.20 sh -c "cp -a /source/. /target/"
    if ($LASTEXITCODE -ne 0) {
        throw "Copy failed for $source -> $target."
    }
}

Write-Host "Volume migration finished. Start the stack and verify each service before deleting old volumes."
