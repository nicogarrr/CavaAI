/**
 * Guard del titular de display de noticias (QW4): el prefijo de ticker
 * solo se omite en titulares generados por CavaAI (flag persistido);
 * los titulares verbatim de la fuente se respetan siempre.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { newsDisplayTitle, untokenizeHeadline } from '../lib/news-display.ts';

const page = (readFileSync('app/(root)/research/news/page.tsx', 'utf8') + readFileSync('components/research/NewsEventsFlow.tsx', 'utf8') + readFileSync('components/research/NewsHeadline.tsx', 'utf8'));

test('omite el prefijo solo en display generado por CavaAI', () => {
    assert.equal(newsDisplayTitle('AAPL 8-K presentado ante la SEC', 'AAPL', false), '8-K presentado ante la SEC');
    assert.equal(newsDisplayTitle('AAPL 8-K presentado ante la SEC', 'AAPL', true), 'AAPL 8-K presentado ante la SEC', 'verbatim intacto');
    assert.equal(newsDisplayTitle('AAPL 8-K presentado ante la SEC', 'AAPL', undefined), 'AAPL 8-K presentado ante la SEC', 'legacy sin flag intacto');
});

test('nunca recorta un titular real aunque empiece por el ticker', () => {
    assert.equal(newsDisplayTitle('AAPL beats estimates', 'AAPL', true), 'AAPL beats estimates');
    // Sin ticker estructural no hay nada que omitir.
    assert.equal(newsDisplayTitle('8-K presentado ante la SEC', null, false), '8-K presentado ante la SEC');
    // El título sin prefijo se queda como está (idempotente).
    assert.equal(newsDisplayTitle('8-K presentado ante la SEC', 'AAPL', false), '8-K presentado ante la SEC');
});

test('límite de palabra: prefijo de ticker, no subcadena', () => {
    // «COSTCO ...» no empieza por el ticker «COST » con espacio.
    assert.equal(newsDisplayTitle('COSTCO abre almacén', 'COST', false), 'COSTCO abre almacén');
    assert.equal(newsDisplayTitle('cost 8-K presentado ante la SEC', 'COST', false), '8-K presentado ante la SEC', 'case-insensitive');
});

test('la tabla de /research/news usa el helper con el flag del payload', () => {
    assert.match(page, /newsDisplayTitle\(event\.title, event\.ticker, event\.headline_from_source\)/);
});

test('F19: titulares tokenizados por la fuente se pintan con la puntuación pegada', () => {
    assert.equal(untokenizeHeadline('AST SpaceMobile , Inc . ( ASTS ) sube un 5 %'), 'AST SpaceMobile, Inc. (ASTS) sube un 5 %');
    assert.equal(newsDisplayTitle('AST SpaceMobile , Inc . ( ASTS )', 'ASTS', true), 'AST SpaceMobile, Inc. (ASTS)');
    // un titular normal no cambia
    assert.equal(untokenizeHeadline('Apple presenta resultados (récord) en EE. UU.'), 'Apple presenta resultados (récord) en EE. UU.');
    // no toca decimales ni miles
    assert.equal(untokenizeHeadline('El PIB crece 1,5 % y 2.5 puntos'), 'El PIB crece 1,5 % y 2.5 puntos');
});
