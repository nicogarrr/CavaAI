#!/bin/sh
# ignoreCommand de Vercel: exit 0 = SALTAR el build, exit 1 = construir.
# Objetivo: no gastar los despliegues diarios del plan en ramas que no tocan el
# front (dependabot de pip/actions, PRs solo de backend, commits vacios de CI).
# Regla: solo se salta con pruebas. Ante cualquier duda, construye.
#
# Base de comparacion: VERCEL_GIT_PREVIOUS_SHA = ultimo despliegue EXITOSO de la
# rama (vacio en el primer despliegue; solo existe con Ignored Build Step). Asi
# un front cambiado en un commit anterior sigue contando aunque el ultimo commit
# sea de backend o este vacio, y un build previo fallido no se da por bueno.
ref="${VERCEL_GIT_COMMIT_REF:-}"
if [ -z "$ref" ] || [ "$ref" = "main" ] || [ "${VERCEL_ENV:-}" = "production" ]; then
  echo "vercel-ignore: main/produccion o rama desconocida -> construir"; exit 1
fi
base="${VERCEL_GIT_PREVIOUS_SHA:-}"
if [ -z "$base" ]; then
  echo "vercel-ignore: sin despliegue previo de la rama -> construir"; exit 1
fi
if ! git cat-file -e "$base^{commit}" 2>/dev/null; then
  echo "vercel-ignore: base $base no disponible en el clon -> construir"; exit 1
fi
if git diff --quiet "$base" HEAD -- . ':(exclude)data-engine' ':(exclude).github' ':(exclude)docs' ':(exclude)infra' ':(exclude)*.md'; then
  echo "vercel-ignore: nada de front desde $base -> saltar"; exit 0
fi
echo "vercel-ignore: cambios de front desde $base -> construir"; exit 1
