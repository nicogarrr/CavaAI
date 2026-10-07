#!/bin/sh
# Prueba de scripts/vercel-ignore.sh en un repo temporal. Uso: sh scripts/vercel-ignore.test.sh
SCRIPT="$(cd "$(dirname "$0")" && pwd)/vercel-ignore.sh"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
cd "$T" && git init -q && git config user.email t@t && git config user.name t || exit 1
mkdir -p app data-engine docs .github; echo a > app/p.tsx; echo a > data-engine/x.py; echo a > docs/d.md
git add -A; git commit -qm base; BASE=$(git rev-parse HEAD)
fail=0
# expect nombre esperado ref previous_sha
expect() {
  VERCEL_GIT_COMMIT_REF="$3" VERCEL_GIT_PREVIOUS_SHA="$4" sh "$SCRIPT" >/dev/null; got=$?
  [ "$got" = "$2" ] || { echo "FALLO $1: esperado $2, obtenido $got"; fail=1; }
}
echo b > data-engine/x.py; git commit -qam be;        expect "solo backend" 0 fix/x "$BASE"
echo b > .github/w.yml; git add -A; git commit -qm ci; expect "backend + .github" 0 dependabot/github_actions/x "$BASE"
echo b >> docs/d.md; git commit -qam doc;             expect "backend + docs" 0 fix/x "$BASE"
git commit -q --allow-empty -m vacio;                 expect "commit vacio" 0 fix/x "$BASE"
echo b > app/p.tsx; git commit -qam front;            expect "front en el ultimo" 1 fix/x "$BASE"
echo c > data-engine/x.py; git commit -qam be2;       expect "multi-commit: front y luego backend" 1 fix/x "$BASE"
git commit -q --allow-empty -m vacio2;                expect "multi-commit: front y luego vacio" 1 fix/x "$BASE"
HEADSHA=$(git rev-parse HEAD)
expect "ya desplegado, sin cambios" 0 fix/x "$HEADSHA"
expect "main siempre construye" 1 main "$HEADSHA"
expect "ref ausente" 1 "" "$HEADSHA"
expect "sin despliegue previo" 1 fix/x ""
expect "base no disponible" 1 fix/x "0000000000000000000000000000000000000001"
VERCEL_ENV=production VERCEL_GIT_COMMIT_REF=fix/x VERCEL_GIT_PREVIOUS_SHA="$HEADSHA" sh "$SCRIPT" >/dev/null; [ $? = 1 ] || { echo "FALLO VERCEL_ENV=production"; fail=1; }
echo '{}' > package.json; git add -A; git commit -qm dep; expect "package.json" 1 dependabot/npm_and_yarn/x "$HEADSHA"
[ "$fail" = 0 ] && echo "OK vercel-ignore" || exit 1
