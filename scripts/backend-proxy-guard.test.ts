/**
 * Guarda del despliegue detrás de Caddy: uvicorn debe confiar en las
 * cabeceras X-Forwarded-* del proxy para que el rate limiter identifique a
 * cada cliente real y no agrupe a todo un tenant en un solo bucket (429 en
 * tormenta con el backend sano).
 * Ejecución: node --experimental-strip-types --test scripts/backend-proxy-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const source = (relativePath: string): string => readFileSync(join(root, relativePath), 'utf8');

describe('backend detrás de Caddy', () => {
  it('uvicorn en producción confía en las cabeceras del proxy', () => {
    const dockerfile = source('data-engine/Dockerfile.prod');
    assert.ok(dockerfile.includes('--proxy-headers'), 'Dockerfile.prod debe arrancar uvicorn con --proxy-headers');
    assert.ok(dockerfile.includes('--forwarded-allow-ips'), 'la confianza debe limitarse a las redes del proxy');
    assert.ok(
      dockerfile.includes('172.16.0.0/12'),
      'el rango por defecto debe cubrir las redes bridge de docker',
    );
  });

  it('el rate limiter identifica por principal + IP real del socket', () => {
    const rateLimit = source('data-engine/app/core/rate_limit.py');
    assert.ok(
      rateLimit.includes('request.client.host'),
      'la identidad del limiter usa la IP del socket (real tras --proxy-headers)',
    );
  });

  it('Caddy termina TLS y reenvía al backend (es quien fija X-Forwarded-For)', () => {
    const caddyfile = source('infra/caddy/Caddyfile');
    assert.ok(caddyfile.includes('reverse_proxy backend:8000'), 'Caddy debe seguir siendo el único ingress');
  });
});
