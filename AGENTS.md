<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes â€” APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` â€” verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Verificación (antes de dar un cambio por bueno)

Todo corre desde la raíz del repo. En verde o el cambio no está terminado:

```bash
& node node_modules\typescript\bin\tsc --noEmit          # tipos
& node node_modules\eslint\bin\eslint.js app components lib hooks scripts
& node --experimental-strip-types --test scripts\*.test.ts   # bundle de guards (glob, auto-descubierto)
& node scripts\check-i18n.mjs                            # claves t() existentes + sin copy en inglés
& node node_modules\next\dist\bin\next build --webpack    # Turbopack FALLA: node_modules es un junction
```

Sin `npm` en el entorno: `bun install` crea `node_modules` (hay `package-lock.json`,
bun lo respeta). Los guards viven en `scripts/*.test.ts` y el glob los descubre
todos: un guard nuevo no se cablea en ninguna lista. El índice de gates (qué
número tumba qué, con runner y umbral) está en
[`docs/QUALITY_GATES.md`](docs/QUALITY_GATES.md).