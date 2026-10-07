#!/bin/sh
# ignoreCommand de Vercel: exit 0 = SALTAR el build, exit 1 = construir.
# Objetivo: no gastar los despliegues diarios del plan en ramas que no tocan el
# front (dependabot de pip/actions, PRs solo de backend, commits vacios de CI).
# Produccion (main) SIEMPRE construye. Ante cualquier duda, construye.
ref="${VERCEL_GIT_COMMIT_REF:-}"
if [ "$ref" = "main" ]; then
  echo "vercel-ignore: main -> construir"; exit 1
fi
if ! git rev-parse --verify -q HEAD^ >/dev/null 2>&1; then
  echo "vercel-ignore: sin HEAD^ (clon superficial) -> construir"; exit 1
fi
if git diff --quiet HEAD^ HEAD -- . ':(exclude)data-engine' ':(exclude).github' ':(exclude)docs' ':(exclude)infra' ':(exclude)*.md'; then
  echo "vercel-ignore: el ultimo commit no toca el front -> saltar"; exit 0
fi
echo "vercel-ignore: cambios de front -> construir"; exit 1
