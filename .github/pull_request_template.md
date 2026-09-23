## Qué cambia

<!-- Resumen en 2-4 líneas -->

## Cómo probarlo

<!-- Pasos o comandos para verificarlo -->

## Checklist

- [ ] Tests añadidos/actualizados y en verde (`pytest tests/ -q`, `npm run test:routes`)
- [ ] Lint y typecheck en verde (`npm run lint`, `npm run typecheck` / `./node_modules/.bin/tsc --noEmit`)
- [ ] Si toca rutas del backend, OpenAPI regenerado sin drift (`npm run generate:openapi` + `git diff --exit-code -- data-engine/openapi.json lib/research/openapi.generated.ts`)
- [ ] Sin secretos, tokens ni `.env` en el diff
- [ ] Migraciones lineales con downgrade si tocan `alembic/versions/`
