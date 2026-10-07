#!/bin/sh
# Prueba de scripts/vercel-ignore.sh en un repo temporal. Uso: sh scripts/vercel-ignore.test.sh
set -e
SCRIPT="$(cd "$(dirname "$0")" && pwd)/vercel-ignore.sh"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
cd "$T"; git init -q; git config user.email t@t; git config user.name t
mkdir -p app data-engine docs .github; echo a > app/p.tsx; echo a > data-engine/x.py; echo a > docs/d.md
git add -A; git commit -qm base
fail=0
expect() { # nombre esperado ref
  VERCEL_GIT_COMMIT_REF="$3" sh "$SCRIPT" >/dev/null; got=$?
  [ "$got" = "$2" ] || { echo "FALLO $1: esperado $2, obtenido $got"; fail=1; }
}
set +e
echo b > data-engine/x.py; git commit -qam be; expect "solo backend" 0 fix/x
echo b > .github/w.yml; git add -A; git commit -qm ci; expect "solo .github" 0 dependabot/github_actions/x
echo b >> docs/d.md; git commit -qam doc; expect "solo docs" 0 fix/x
git commit -q --allow-empty -m vacio; expect "commit vacio" 0 fix/x
echo b > app/p.tsx; git commit -qam front; expect "front" 1 fix/x
echo '{}' > package.json; git add -A; git commit -qm dep; expect "package.json" 1 dependabot/npm_and_yarn/x
echo c > data-engine/x.py; git commit -qam be2; expect "main siempre construye" 1 main
echo n > nuevo.ts; git add -A; git commit -qm nuevo; expect "fichero nuevo en raiz" 1 fix/x
cd "$T" && rm -rf .git && git init -q && git config user.email t@t && git config user.name t && echo a > a && git add -A && git commit -qm unico
expect "sin HEAD^" 1 fix/x
[ "$fail" = 0 ] && echo "OK vercel-ignore" || exit 1
