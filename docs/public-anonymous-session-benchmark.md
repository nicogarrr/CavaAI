# Sesión de visitante sin Cookie: evitar inicialización de Mongo

Fecha: 2026-10-16. Control exacto: `cfecb5f0139d0f7c30e459a256b5e24924103a2a`.
Candidato: el parche de esta PR, construido sobre ese control. Ambos builds con
`npm run build` y servidor standalone de producción, en la misma VM.

## Qué se mide y qué NO

Canario de **fallo controlado**, NO benchmark de Vercel. Mongo apunta a un puerto
loopback sin servidor (`mongodb://127.0.0.1:27029/cava_perf_absent`). Ninguna cuenta,
ningún dato de producción, ningún registro/login y ningún bypass E2E. Los secretos
son aleatorios y efímeros. No se modificó configuración de producción.

Una muestra por ruta/build, `curl time_starttransfer`, sin Cookie. Procesos recién
arrancados; `/sign-in` es la primera petición y `/` la segunda en cada proceso.
No son medianas ni una simulación del rendimiento típico con Mongo disponible.
Muestras y marcas UTC completas en `public-anonymous-session-samples.json`.

| Ruta | Base HTTP | Base TTFB | Candidato HTTP | Candidato TTFB |
| --- | ---: | ---: | ---: | ---: |
| `/sign-in` | 500 | 30.759644 s | 200 | 0.594934 s |
| `/` | 200 | 30.090782 s | 200 | 0.070950 s |

El log del candidato fresco no muestra inicialización/conexión de Mongo tras las
dos peticiones sin Cookie. La mejora demostrada es eliminar esa dependencia para
visitantes sin Cookie y evitar que un fallo de DB rompa su pantalla de login.
No demuestra una mejora de LCP, de JS inicial, de usuarios autenticados ni de TTFB
normal en el alias público. Cualquier Cookie no vacía conserva el coste original.

## Alcance y seguridad

- El helper solo evita `getAuth()` cuando el encabezado Cookie está ausente, vacío
  o compuesto de espacios. No analiza tokens ni concede identidad.
- Cookie presente, incluso desconocida o malformada: se ejecuta la validación
  original completa. La configuración actual de Better Auth usa cookies (plugins
  `nextCookies` y `twoFactor`, no plugin bearer).
- Se aplica al layout público, layout de auth y la segunda comprobación de sesión
  de la landing. Mantiene los redirects y el manejo original de errores.
- El layout privado sigue llamando a `requireAuthenticatedUser()` sin cambios.
- Con `Cookie: unrelated=1` y DB caída, el canario de login conserva HTTP 500 tras
  unos 30 segundos; no se transforma una comprobación fallida en sesión válida.
- Sin configuración válida de runtime, la validación de `env` puede seguir fallando
  al importar auth. No es un mecanismo de recuperación de configuración ni de DB.

## Validación

- Build de producción: exit 0, TypeScript incluido.
- Helper y guards de redirect: 11/11. La nueva prueba se descubre automáticamente
  por `npm run test:guards`.
- Suite completa: 1148/1148, exit 0, con git y Python disponibles.
  La primera ejecución aislada carecía de git/Python; no se atribuyen esos fallos
  de entorno a código previo ni se ocultan como una suite verde.
- ESLint de todos los archivos modificados: exit 0.
- Integración contra standalone real y Mongo inalcanzable: 4/4. Tres rutas públicas
  sin Cookie responden 200 en menos del timeout de 10 s; con Cookie auth mantiene
  su error de DB. No usa `E2E_AUTH_BYPASS`.
- Capturas reales de navegador de landing 390/1280 y login 390: HTTP 200, fuentes
  cargadas, sin desbordamiento; inspección visual sin cambios de diseño.

Reproducción del canario (solo servidor local aislado, con el URI anterior):

```sh
E2E_ANON_OUTAGE_URL=http://127.0.0.1:3115 npx playwright test e2e/anonymous-public.spec.ts --workers 1
curl -sS --max-time 40 -o /dev/null -w '%{http_code} %{time_starttransfer}\n' http://127.0.0.1:3115/sign-in
curl -sS --max-time 40 -o /dev/null -w '%{http_code} %{time_starttransfer}\n' http://127.0.0.1:3115/
```

El test rechaza destinos que no sean HTTP loopback. No ejecutar el canario sobre
producción. Los contenedores temporales se paran al acabar la validación.
