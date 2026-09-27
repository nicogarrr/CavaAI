/**
 * Guard F249 (lista de Documentos accionable): cada ficha enlaza a la
 * fuente primaria cuando el documento tiene source_url (los filings SEC
 * la traen); sin URL queda texto, nunca un enlace roto ni un div
 * estático con URL disponible. Enlaces externos con rel="noopener
 * noreferrer" y target="_blank".
 *
 * Ejecucion: node --experimental-strip-types --test scripts/documents-list-links-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const page = readFileSync('app/(root)/research/[ticker]/page.tsx', 'utf8');

// Aisla el bloque de la lista de documentos
const listMatch = page.match(/title="Documentos"[\s\S]{0,2200}/);
assert.ok(listMatch, 'no se encontró el panel Documentos');
const block = listMatch[0];

describe('documents list links guard (F249)', () => {
  it('la ficha enlaza cuando hay source_url', () => {
    assert.match(block, /document\.source_url \? <a/, 'condicional sobre source_url');
    assert.match(block, /href=\{document\.source_url\}/, 'href desde source_url');
  });

  it('sin URL queda texto, no enlace roto', () => {
    assert.match(block, /: <span className="font-medium text-gray-200">\{document\.title\}<\/span>/, 'fallback a texto');
  });

  it('enlace externo seguro', () => {
    assert.match(block, /target="_blank"/);
    assert.match(block, /rel="noopener noreferrer"/);
  });
});
