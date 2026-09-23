/*
 * CavaAI — service worker mínimo.
 * Alcance deliberadamente pequeño:
 *   1) App shell: precache de '/' + caché runtime de estáticos inmutables
 *      (/_next/static/, /assets/).
 *   2) Fallback offline: toda navegación que falle por red sirve el shell
 *      cacheado y, si no existe, una página offline sintética.
 * NADA de lo autenticado se cachea: server actions, /api/* y respuestas con
 * cabecera Set-Cookie pasan directamente a la red.
 */
const CACHE = 'cavaai-shell-v1';
const APP_SHELL = ['/'];
const OFFLINE_HTML =
  '<!doctype html><html lang="es"><meta charset="utf-8">' +
  '<meta name="viewport" content="width=device-width, initial-scale=1">' +
  '<title>CavaAI — sin conexión</title>' +
  '<body style="background:#101010;color:#d1d5db;font-family:system-ui,sans-serif;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0">' +
  '<div style="text-align:center;padding:24px">' +
  '<h1 style="font-size:20px;color:#f3f4f6">Sin conexión</h1>' +
  '<p style="font-size:14px;color:#9ca3af">CavaAI necesita red para leer tus tesis y datos de mercado.<br>Reconecta y vuelve a intentarlo.</p>' +
  '</div></body></html>';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(APP_SHELL))
      .catch(() => undefined) // el shell es best-effort: nunca bloquea la instalación
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

function isImmutableStatic(url) {
  return (
    url.origin === self.location.origin &&
    (url.pathname.startsWith('/_next/static/') || url.pathname.startsWith('/assets/'))
  );
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // APIs externas: fuera
  if (url.pathname.startsWith('/api/')) return; // datos vivos: nunca cache
  if (isImmutableStatic(url)) {
    // Estáticos con hash en el nombre: cache-first (son inmutables).
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((response) => {
            if (response.ok) {
              const copy = response.clone();
              caches.open(CACHE).then((cache) => cache.put(request, copy));
            }
            return response;
          })
      )
    );
    return;
  }

  if (request.mode === 'navigate') {
    // Navegaciones: red primero, shell cacheado como fallback.
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put('/', copy));
          }
          return response;
        })
        .catch(
          () =>
            caches.match('/') ||
            new Response(OFFLINE_HTML, { headers: { 'Content-Type': 'text/html; charset=utf-8' } })
        )
    );
  }
});
