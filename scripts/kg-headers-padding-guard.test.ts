/**
 * Guard F312: Confianza y Procedencia no quedan pegadas en la tabla de
 * relaciones del grafo de conocimiento.
 *
 * Confianza va alineada a la derecha y Procedencia a la izquierda: sin padding
 * horizontal los dos textos se tocaban en el borde compartido
 * (Â«CONFIANZAPROCEDENCIAÂ») a cualquier ancho (confirmado 1440 y 1920).
 *
 * Lo que este guard protege es el PADDING, no la cadena literal con la que se
 * imprime la confianza. FIX6 sustituyo `{(Number(edge.confidence)*100).toFixed(0)}%`
 * por `{formatConfidence(edge.confidence)}` (una sola verdad de formato, y el
 * valor deja de mentir cuando la confianza llega ya expresada en porcentaje)
 * y el invariante de padding no cambio ni un pixel. Un guard que fija la
 * cadena literal tumbaria una mejora de producto; uno que solo mira "que haya
 * un formatConfidence" no distinguiria el cambio bueno del malo.
 *
 * Asi que el detector separa las dos cosas: exige la clase de padding en la
 * celda correcta (el invariante) y acepta CUALQUIER forma de imprimir el
 * valor (que no lo es). Y al final se muta una COPIA de la pagina para
 * comprobar que el detector sigue viendo el antipatron: un guard que no muerde
 * contra la mutacion no esta vigilando nada.
 *
 * Ejecucion: node --experimental-strip-types --test scripts/kg-headers-padding-guard.test.ts
 */
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import test from 'node:test';

const PAGE_URL = new URL('../app/(root)/knowledge-graph/page.tsx', import.meta.url);
const page = readFileSync(PAGE_URL, 'utf8');

/* ------------------------------------------------------------------ *
 * Detector. Empareja clase y contenido de la MISMA celda: mirar el
 * `px-3` de cualquier parte de la pagina absolveria a la celda de al
 * lado, que es justo el bug (una pegada compensa a la otra).
 * ------------------------------------------------------------------ */

/** Formas aceptadas de imprimir la confianza de una arista. */
const CONFIANZA = /formatConfidence\(\s*edge\.confidence\s*\)|Number\(\s*edge\.confidence\s*\)\s*\*\s*100/;
const PROCEDENCIA = /edge\.provenance/;

/**
 * Las cuatro celdas que comparten el borde confidenciaprocedencia, cada una
 * con el padding horizontal que la separa de su vecina.
 */
const REGLAS = [
  { celda: 'cabecera de Confianza', contenido: /^\s*Confianza\s*$/, padding: /\bpx-3\b/, motivo: 'px-3 a la derecha' },
  { celda: 'cabecera de Procedencia', contenido: /^\s*Procedencia\s*$/, padding: /\bpl-3\b/, motivo: 'pl-3 a la izquierda' },
  { celda: 'celda de Confianza', contenido: CONFIANZA, padding: /\bpx-3\b/, motivo: 'px-3 a la derecha' },
  { celda: 'celda de Procedencia', contenido: PROCEDENCIA, padding: /\bpl-3\b/, motivo: 'pl-3 a la izquierda' },
] as const;

/** Celdas de tabla (`td`/`th`) con su clase y su cuerpo. */
function celdas(source: string): Array<{ clase: string; cuerpo: string }> {
  const out: Array<{ clase: string; cuerpo: string }> = [];
  for (const m of source.matchAll(/<(?:td|th)\s+className="([^"]*)"[^>]*>([\s\S]*?)<\/(?:td|th)>/g)) {
    out.push({ clase: m[1] ?? '', cuerpo: m[2] ?? '' });
  }
  return out;
}

/** Hallazgos: celda ausente, o celda presente sin su padding horizontal. */
export function findCeldasPegadas(source: string): string[] {
  const hallazgos: string[] = [];
  const todas = celdas(source);
  for (const regla of REGLAS) {
    const propias = todas.filter((c) => regla.contenido.test(c.cuerpo));
    if (!propias.length) {
      hallazgos.push(`${regla.celda}: no se encuentra en la tabla`);
      continue;
    }
    for (const celda of propias) {
      if (!regla.padding.test(celda.clase)) {
        hallazgos.push(
          `${regla.celda} sin ${regla.motivo}, se pega con la vecina (className="${celda.clase}")`,
        );
      }
    }
  }
  return hallazgos;
}

/* ------------------------------------------------------------------ *
 * La pagina real.
 * ------------------------------------------------------------------ */

test('F312: Confianza y Procedencia no quedan pegadas en la tabla de relaciones', () => {
  assert.deepEqual(findCeldasPegadas(page), [], 'Confianza y Procedencia necesitan padding propio en las cuatro celdas');
});

test('F312: la confianza se imprime con una sola verdad de formato', () => {
  // El contenido de la celda puede cambiar (FIX6 paso a `formatConfidence`), pero
  // tiene que SEGUIR siendo la confianza de la arista: un `{edge.type}` en esa
  // celda pasaria el invariante de padding y estaria pintando otra cosa.
  const propias = celdas(page).filter((c) => CONFIANZA.test(c.cuerpo));
  assert.ok(propias.length >= 1, 'debe existir la celda de confianza de la fila');
  for (const celda of propias) assert.match(celda.cuerpo, CONFIANZA);
});

/* ------------------------------------------------------------------ *
 * Caso negativo: el detector tiene que VER el antipatron. Se muta una
 * copia de la pagina real (quitar el padding de las celdas con padding
 * horizontal) y se comprueba que el guard muerde.
 * ------------------------------------------------------------------ */

/** Quita el padding horizontal (`px-3`/`pl-3`) de todas las celdas que lo tengan. */
function sinPaddingHorizontal(source: string): string {
  return source.replace(
    /(<(?:td|th)\s+className=")([^"]*)(")/g,
    (todo, apertura: string, clase: string, cierre: string) =>
      `${apertura}${clase.replace(/\b(?:px|pl)-3\b/g, '').replace(/\s+/g, ' ').trim()}${cierre}`,
  );
}

test('F312: el guard muerde si vuelven a pegarse las celdas (mutacion)', () => {
  const mutada = sinPaddingHorizontal(page);
  assert.notEqual(mutada, page, 'la mutacion tiene que cambiar la pagina de verdad');
  const hallazgos = findCeldasPegadas(mutada);
  assert.ok(hallazgos.length > 0, `el detector debe ver las celdas pegadas: ${JSON.stringify(hallazgos)}`);
  assert.match(hallazgos.join('\n'), /celda de Confianza sin px-3/);
  assert.match(hallazgos.join('\n'), /celda de Procedencia sin pl-3/);
  assert.match(hallazgos.join('\n'), /cabecera de Confianza sin px-3/);
  assert.match(hallazgos.join('\n'), /cabecera de Procedencia sin pl-3/);
});

test('F312: el detector distingue celda sin padding de celda que no existe', () => {
  const sinConfianza = page.replace(/<td className="px-3 py-3 text-right text-gray-400">\{formatConfidence\(edge\.confidence\)\}<\/td>/, '');
  assert.notEqual(sinConfianza, page, 'la mutacion tiene que quitar la celda de verdad');
  const hallazgos = findCeldasPegadas(sinConfianza);
  assert.match(hallazgos.join('\n'), /celda de Confianza: no se encuentra/);
});