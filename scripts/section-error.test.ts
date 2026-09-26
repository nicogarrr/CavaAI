/**
 * sectionError: el usuario ve un mensaje generico por categoria, nunca el
 * error crudo (URLs, rutas internas, fragments de respuesta).
 * Ejecucion: node --experimental-strip-types --test scripts/section-error.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
// @ts-expect-error TS5097: la extension explicita la exige node --experimental-strip-types.
import { sectionError } from '../lib/section-error.ts';

describe('sectionError', () => {
    it('no expone el mensaje crudo del error', () => {
        const raw = 'GET https://api.internal.example/v1/quotes?token=SECRET failed with 502 Bad Gateway: {"trace":"abc"}';
        const shown = sectionError(new Error(raw));
        assert.ok(!shown.includes('api.internal.example'));
        assert.ok(!shown.includes('SECRET'));
        assert.ok(!shown.includes('trace'));
    });
    it('categoriza fallos de red', () => {
        assert.match(sectionError(new Error('fetch failed')), /conectar/);
        assert.match(sectionError(new Error('ECONNREFUSED')), /conectar/);
        assert.match(sectionError(new Error('request timeout')), /conectar/);
    });
    it('categoriza sesion caducada', () => {
        assert.match(sectionError(new Error('401 Unauthorized')), /sesion/);
        assert.match(sectionError(new Error('403 forbidden')), /sesion/);
    });
    it('categoriza fallos del servicio', () => {
        assert.match(sectionError(new Error('502 Bad Gateway')), /servicio ha fallado/);
        assert.match(sectionError(new Error('Internal Server Error')), /servicio ha fallado/);
    });
    it('cae al mensaje generico ante errores no Error o desconocidos', () => {
        assert.match(sectionError('boom'), /No se pudieron cargar/);
        assert.match(sectionError(new Error('something odd')), /No se pudieron cargar/);
        assert.match(sectionError(undefined), /No se pudieron cargar/);
    });
});
