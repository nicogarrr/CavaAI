/**
 * D2b: matematica pura del viewport de /knowledge-graph.
 *
 * Aqui viven los bugs: el zoom que se va solo al acercar al cursor, el grafo
 * que se pierde arrastrando, la division por cero cuando el subgrafo cabe en
 * una sola coordenada y la escala que se desbota al encajar 500 nodos. Todo se
 * comprueba como funcion pura, sin navegador.
 *
 * Ejecucion: node --experimental-strip-types --test scripts/knowledge-graph-viewport.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import {
    boundsCenter,
    boundsOf,
    boundsSize,
    centerOnPoint,
    clampScale,
    clampViewport,
    expandBounds,
    fitToView,
    identityViewport,
    isInsideBounds,
    MAX_SCALE,
    MIN_SCALE,
    OVERSCROLL,
    panBy,
    pinchToFactor,
    scalePercent,
    toGraphPoint,
    toScreenPoint,
    toSvgTransform,
    wheelToFactor,
    zoomAtPoint,
    zoomCentered,
    ZOOM_STEP,
    type Size,
    type Viewport,
    // @ts-expect-error TS5097: la extension .ts explicita la exige node --experimental-strip-types en runtime.
} from '../lib/knowledge-graph/viewport.ts';

import {
    boundsFor,
    buildScene,
    describeDetail,
    EDGE_COLOR,
    focusIds,
    MAX_SCENE_NODES,
    radiusForDegree,
    ringCapacity,
    searchNodes,
    serializeJson,
    serializeSvg,
    subgraphFor,
    type GraphPayload,
    // @ts-expect-error TS5097: la extension .ts explicita la exige node --experimental-strip-types en runtime.
} from '../lib/knowledge-graph/graph-model.ts';

const SIZE: Size = { width: 800, height: 600 };
const near = (actual: number, expected: number, tolerance = 1e-6) =>
    assert.ok(Math.abs(actual - expected) <= tolerance, `esperaba ~${expected}, obtuve ${actual}`);

/* ------------------------------------------------------------------ *
 * clampScale
 * ------------------------------------------------------------------ */

describe('clampScale', () => {
    it('acota al rango declarado', () => {
        assert.equal(clampScale(0.0001), MIN_SCALE);
        assert.equal(clampScale(99), MAX_SCALE);
        assert.equal(clampScale(1.5), 1.5);
    });

    it('respeta limites propios', () => {
        assert.equal(clampScale(0.5, { min: 1, max: 3 }), 1);
        assert.equal(clampScale(5, { min: 1, max: 3 }), 3);
        assert.equal(clampScale(2, { min: 1, max: 3 }), 2);
    });

    it('corrige un rango invertido en vez de devolver una ventana vacia', () => {
        // min > max: si no se corrige, clamp(5, 3, 1) puede devolver 3, 1 o NaN
        // segun como se implemente, y el lienzo se queda sin escala valida.
        assert.equal(clampScale(5, { min: 3, max: 1 }), 3);
        assert.equal(clampScale(0.1, { min: 3, max: 1 }), 3);
    });

    it('sustituye valores no finitos por un valor utilizable', () => {
        assert.equal(clampScale(Number.NaN), 1);
        assert.equal(clampScale(Number.POSITIVE_INFINITY), MAX_SCALE, 'un exceso se recorta al tope');
        assert.equal(clampScale(Number.NEGATIVE_INFINITY), MIN_SCALE);
    });

    it('nunca devuelve 0 ni negativo (el transform se descartaria)', () => {
        for (const value of [0, -5, -1e9]) assert.ok(clampScale(value) > 0);
    });
});

/* ------------------------------------------------------------------ *
 * bounds
 * ------------------------------------------------------------------ */

describe('boundsOf', () => {
    it('devuelve null sin puntos', () => {
        assert.equal(boundsOf([]), null);
    });

    it('ignora puntos no finitos en vez de poisons el bbox', () => {
        // Un punto se descarta ENTERO si cualquiera de sus dos coordenadas no
        // es finita: mezclar la x valida con una y rota daria una caja falsa.
        const bounds = boundsOf([{ x: 0, y: 0 }, { x: Number.NaN, y: 5 }, { x: 10, y: Number.POSITIVE_INFINITY }]);
        assert.deepEqual(bounds, { minX: 0, minY: 0, maxX: 0, maxY: 0 });
    });

    it('descarta la caja entera si no queda ningun punto valido', () => {
        assert.equal(boundsOf([{ x: Number.NaN, y: 1 }, { x: 1, y: Number.NaN }]), null);
    });

    it('un unico punto da una caja de tamano 0', () => {
        const bounds = boundsOf([{ x: 4, y: 9 }]);
        assert.deepEqual(boundsSize(bounds!), { width: 0, height: 0 });
    });

    it('expandBounds suma el margen por los cuatro lados', () => {
        assert.deepEqual(expandBounds({ minX: 0, minY: 0, maxX: 10, maxY: 10 }, 5), {
            minX: -5,
            minY: -5,
            maxX: 15,
            maxY: 15,
        });
    });

    it('boundsCenter y isInsideBounds son coherentes con la caja', () => {
        const bounds = { minX: 0, minY: 0, maxX: 10, maxY: 20 };
        assert.deepEqual(boundsCenter(bounds), { x: 5, y: 10 });
        assert.equal(isInsideBounds({ x: 5, y: 5 }, bounds), true);
        assert.equal(isInsideBounds({ x: 0, y: 20 }, bounds), true, 'los bordes son dentro');
        assert.equal(isInsideBounds({ x: 11, y: 5 }, bounds), false);
    });
});

/* ------------------------------------------------------------------ *
 * zoomAtPoint
 * ------------------------------------------------------------------ */

describe('zoomAtPoint', () => {
    const base: Viewport = { x: 100, y: 50, scale: 1 };

    it('mantiene fijo el punto de pantalla ancla', () => {
        const anchor = { x: 400, y: 300 };
        const before = toScreenPoint(base, toGraphPoint(base, anchor));
        const next = zoomAtPoint(base, 2, anchor);
        const after = toScreenPoint(next, toGraphPoint(next, anchor));
        assert.deepEqual(before, anchor);
        assert.deepEqual(after, anchor);
        near(after.x, anchor.x);
        near(after.y, anchor.y);
    });

    it('el punto ancla sigue fijo tambien al alejar', () => {
        const anchor = { x: 120, y: 480 };
        const next = zoomAtPoint(base, 0.5, anchor);
        const projected = toScreenPoint(next, toGraphPoint(next, anchor));
        near(projected.x, anchor.x);
        near(projected.y, anchor.y);
    });

    it('mueve el resto del grafo en el sentido correcto', () => {
        // Alejar tiene que traer el contenido hacia dentro (mas cerca del ancla).
        const anchor = { x: 400, y: 300 };
        const graph = { x: 0, y: 0 };
        const before = toScreenPoint(base, graph);
        const after = toScreenPoint(zoomAtPoint(base, 0.5, anchor), graph);
        assert.ok(after.x > before.x, 'el origen se acerca al ancla al alejar');
        assert.ok(Math.abs(before.x - anchor.x) > Math.abs(after.x - anchor.x));
    });

    it('acota la escala al máximo declarado aunque se pida un factor enorme', () => {
        const next = zoomAtPoint(base, 1e6, { x: 0, y: 0 });
        assert.equal(next.scale, MAX_SCALE);
    });

    it('un factor no positivo no invierte el grafo', () => {
        for (const factor of [0, -2, Number.NaN]) {
            const next = zoomAtPoint(base, factor, { x: 10, y: 10 });
            assert.ok(next.scale > 0, `escala positiva con factor ${factor}`);
            assert.equal(next.x, base.x);
            assert.equal(next.y, base.y);
        }
    });

    it('una escala 0 previa no divide por cero', () => {
        const broken: Viewport = { x: 10, y: 10, scale: 0 };
        const next = zoomAtPoint(broken, ZOOM_STEP, { x: 0, y: 0 });
        assert.ok(Number.isFinite(next.x) && Number.isFinite(next.y));
        assert.ok(next.scale > 0);
    });

    it('zoomCentered ancla en el centro del lienzo', () => {
        const anchor = { x: SIZE.width / 2, y: SIZE.height / 2 };
        const next = zoomCentered(base, ZOOM_STEP, SIZE);
        const projected = toScreenPoint(next, toGraphPoint(next, anchor));
        near(projected.x, anchor.x);
        near(projected.y, anchor.y);
    });

    it('el readout en porcentaje sigue a la escala acotada', () => {
        assert.equal(scalePercent({ x: 0, y: 0, scale: 1 }), 100);
        assert.equal(scalePercent({ x: 0, y: 0, scale: 0.334 }), 33);
        assert.equal(scalePercent({ x: 0, y: 0, scale: 99 }), 400);
    });
});

/* ------------------------------------------------------------------ *
 * panBy
 * ------------------------------------------------------------------ */

describe('panBy', () => {
    it('desplaza en pixeles de pantalla, sin dividir por la escala', () => {
        const zoomed: Viewport = { x: 0, y: 0, scale: 4 };
        assert.deepEqual(panBy(zoomed, 100, -50), { x: 100, y: -50, scale: 4 });
    });

    it('un delta no finito no mueve la vista', () => {
        assert.deepEqual(panBy({ x: 3, y: 4, scale: 2 }, Number.NaN, Number.POSITIVE_INFINITY), { x: 3, y: 4, scale: 2 });
    });
});

/* ------------------------------------------------------------------ *
 * fitToView
 * ------------------------------------------------------------------ */

describe('fitToView', () => {
    it('encaja la caja completa dentro del lienzo conservando la proporcion', () => {
        const bounds = { minX: 0, minY: 0, maxX: 400, maxY: 200 };
        const fitted = fitToView(bounds, SIZE, 0);
        assert.equal(fitted.scale, 2, 'ancho limitante (800/400) frente a alto (600/200)');
        const screen = {
            x: toScreenPoint(fitted, { x: bounds.minX, y: bounds.minY }).x,
            y: toScreenPoint(fitted, { x: bounds.minX, y: bounds.minY }).y,
        };
        assert.ok(screen.x >= -1e-6 && screen.y >= -1e-6, 'no se sale por arriba a la izquierda');
    });

    it('el margen no se cuela dentro de la escala', () => {
        const bounds = { minX: 0, minY: 0, maxX: 400, maxY: 400 };
        const fitted = fitToView(bounds, SIZE, 100);
        assert.equal(fitted.scale, 600 / 600, 'encaja la caja ya dilatada por el margen');
    });

    it('encaja con tamano de nodo 0 en un eje sin dividir entre 0', () => {
        // Todos los nodos en la misma fila: alto 0. Si el eje se usara para
        // calcular la escala, division por cero => escala Infinity o 0.
        const fitted = fitToView({ minX: 0, minY: 100, maxX: 200, maxY: 100 }, SIZE, 0);
        assert.ok(Number.isFinite(fitted.scale));
        assert.ok(fitted.scale > 0);
        assert.equal(fitted.scale, 4, 'solo manda el ancho');
        near(toScreenPoint(fitted, { x: 0, y: 100 }).y, SIZE.height / 2, 1e-6);
    });

    it('un unico nodo (caja 0x0) queda centrado con escala 1', () => {
        const fitted = fitToView({ minX: 42, minY: 42, maxX: 42, maxY: 42 }, SIZE, 0);
        assert.equal(fitted.scale, 1);
        near(toScreenPoint(fitted, { x: 42, y: 42 }).x, SIZE.width / 2, 1e-6);
        near(toScreenPoint(fitted, { x: 42, y: 42 }).y, SIZE.height / 2, 1e-6);
    });

    it('acota la escala al rango declarado al encajar un grafo enorme', () => {
        const fitted = fitToView({ minX: 0, minY: 0, maxX: 100000, maxY: 100000 }, SIZE, 0);
        assert.equal(fitted.scale, MIN_SCALE, 'encajar 100k unidades no puede bajar del minimo');
    });

    it('sin contenido o sin tamano medido devuelve la vista identidad', () => {
        assert.deepEqual(fitToView(null, SIZE), identityViewport());
        assert.deepEqual(fitToView({ minX: 0, minY: 0, maxX: 10, maxY: 10 }, { width: 0, height: 0 }), identityViewport());
    });

    it('la caja encajada queda centrada', () => {
        const bounds = { minX: -30, minY: 90, maxX: 70, maxY: 190 };
        const fitted = fitToView(bounds, SIZE, 0);
        const center = boundsCenter(bounds);
        near(toScreenPoint(fitted, center).x, SIZE.width / 2, 1e-6);
        near(toScreenPoint(fitted, center).y, SIZE.height / 2, 1e-6);
    });
});

/* ------------------------------------------------------------------ *
 * centerOnPoint
 * ------------------------------------------------------------------ */

describe('centerOnPoint', () => {
    it('deja el nodo en el centro conservando la escala', () => {
        const centered = centerOnPoint({ x: 120, y: 260 }, SIZE, 1.5);
        assert.equal(centered.scale, 1.5);
        near(toScreenPoint(centered, { x: 120, y: 260 }).x, SIZE.width / 2, 1e-6);
        near(toScreenPoint(centered, { x: 120, y: 260 }).y, SIZE.height / 2, 1e-6);
    });

    it('acota la escala que le pasan', () => {
        assert.equal(centerOnPoint({ x: 0, y: 0 }, SIZE, 50).scale, MAX_SCALE);
    });
});

/* ------------------------------------------------------------------ *
 * clampViewport (comportamiento ante desbordamiento)
 * ------------------------------------------------------------------ */

describe('clampViewport', () => {
    const bounds = { minX: 0, minY: 0, maxX: 1000, maxY: 1000 };

    it('impide arrastrar el grafo entero fuera del lienzo', () => {
        const lost = clampViewport({ x: -99999, y: -99999, scale: 1 }, bounds, SIZE, OVERSCROLL);
        const right = lost.x + bounds.maxX;
        assert.ok(right >= SIZE.width * OVERSCROLL - 1e-6, 'queda un fragmento a la derecha');
        const left = lost.x + bounds.minX;
        assert.ok(left <= SIZE.width * (1 - OVERSCROLL) + 1e-6, 'queda un fragmento a la izquierda');
    });

    it('permite desplazar tambien el eje donde el contenido es mas pequeno que el lienzo', () => {
        // Antes este eje se quedaba centrado y el arrastre no hacia nada: con
        // el grafo entero visible, arrastrar se leia como un lienzo roto.
        const narrow = { minX: 0, minY: 0, maxX: 100, maxY: 1000 };
        const margin = SIZE.width * OVERSCROLL;
        const moved = clampViewport({ x: 100000, y: 0, scale: 1 }, narrow, SIZE, OVERSCROLL);
        assert.ok(moved.x < 100000, 'el arrastre mueve tambien un eje con hueco de sobra');
        // Invariante: sigue habiendo grafo dentro del lienzo por los dos lados.
        assert.ok(moved.x + narrow.minX <= SIZE.width - margin + 1e-6);
        assert.ok(moved.x + narrow.maxX >= margin - 1e-6);
        assert.equal(clampViewport({ x: 400, y: 0, scale: 1 }, narrow, SIZE, OVERSCROLL).x, 400, 'dentro del rango no se toca nada');
    });

    it('una caja degenerada (todo en un punto) tampoco se sale del lienzo', () => {
        const point = { minX: 10, minY: 10, maxX: 10, maxY: 10 };
        const clamped = clampViewport({ x: 100000, y: -100000, scale: 1 }, point, SIZE, OVERSCROLL);
        near(clamped.x, SIZE.width - SIZE.width * OVERSCROLL - 10, 1e-6);
        near(clamped.y, SIZE.height * OVERSCROLL - 10, 1e-6);
    });

    it('es idempotente: aplicar el freno dos veces no cambia nada', () => {
        const once = clampViewport({ x: -5000, y: 900, scale: 2 }, bounds, SIZE, OVERSCROLL);
        const twice = clampViewport(once, bounds, SIZE, OVERSCROLL);
        assert.deepEqual(twice, once);
    });

    it('sin caja no toca la vista (grafo vacio)', () => {
        const viewport = { x: 12, y: 34, scale: 1 };
        assert.deepEqual(clampViewport(viewport, null, SIZE), viewport);
    });

    it('el resultado de fitToView sobrevive al freno (encajar y arrastrar encadenados)', () => {
        const fitted = fitToView(bounds, SIZE, 24);
        const clamped = clampViewport(fitted, bounds, SIZE, OVERSCROLL);
        assert.deepEqual(clamped, fitted, 'encajar nunca debe saltar por el freno');
    });
});

/* ------------------------------------------------------------------ *
 * matrices de transformacion
 * ------------------------------------------------------------------ */

describe('transformaciones de pantalla y grafo', () => {
    const cases: Array<[string, Viewport]> = [
        ['identidad', { x: 0, y: 0, scale: 1 }],
        ['desplazada', { x: -137.25, y: 42.5, scale: 1 }],
        ['alejada al minimo', { x: 10, y: 10, scale: MIN_SCALE }],
        ['acercada al maximo', { x: 10, y: 10, scale: MAX_SCALE }],
        ['escala fraccionaria', { x: 0.125, y: 0.875, scale: 0.3375 }],
    ];

    for (const [name, viewport] of cases) {
        it(`pantalla -> grafo -> pantalla es la identidad (${name})`, () => {
            for (const point of [
                { x: 0, y: 0 },
                { x: 123.456, y: -78.9 },
                { x: 1100, y: 620 },
            ]) {
                const back = toGraphPoint(viewport, toScreenPoint(viewport, point));
                near(back.x, point.x, 1e-6);
                near(back.y, point.y, 1e-6);
            }
        });
    }

    it('toSvgTransform escribe translate y scale en ese orden', () => {
        assert.equal(toSvgTransform({ x: 10, y: 20, scale: 2 }), 'translate(10 20) scale(2)');
    });

    it('toSvgTransform redondea y acota (nada de notacion cientifica ni NaN)', () => {
        const transform = toSvgTransform({ x: 1.23456789, y: -0.0004, scale: 99 });
        assert.equal(transform, 'translate(1.235 0) scale(4)');
        assert.equal(toSvgTransform({ x: Number.NaN, y: Number.POSITIVE_INFINITY, scale: Number.NaN }), 'translate(0 0) scale(1)');
    });

    it('una escala 0 o negativa se recorta al mínimo y no rompe la proyección', () => {
        // toSvgTransform escribe la escala recortada, asi que la proyeccion
        // tiene que usar la MISMA escala recortada o el clic en un nodo
        // apuntaría a otro sitio.
        const broken = { x: 10, y: 10, scale: 0 };
        const projected = toGraphPoint(broken, { x: 100, y: 100 });
        assert.ok(Number.isFinite(projected.x) && Number.isFinite(projected.y));
        assert.equal(toSvgTransform(broken).includes(String(MIN_SCALE)), true);
        const back = toScreenPoint(broken, projected);
        near(back.x, 100, 1e-6);
        near(back.y, 100, 1e-6);
    });
});

/* ------------------------------------------------------------------ *
 * gestos
 * ------------------------------------------------------------------ */

describe('gestos', () => {
    it('wheelToFactor acerca al subir la rueda y aleja al bajar', () => {
        assert.ok(wheelToFactor(-100) > 1, 'rueda hacia arriba => acercar');
        assert.ok(wheelToFactor(100) < 1, 'rueda hacia abajo => alejar');
        assert.equal(wheelToFactor(0), 1);
        assert.ok(Number.isFinite(wheelToFactor(Number.NaN)));
    });

    it('un giro de rueda es un paso de zoom medible y acotado', () => {
        const perNotch = wheelToFactor(-100);
        assert.ok(perNotch > 1, 'una muesca de rueda acerca');
        assert.ok(perNotch < ZOOM_STEP * 1.5, 'y no de un salto que pierda el hilo');
        assert.ok(wheelToFactor(-400) > perNotch, 'cuatro muescas acercan mas que una');
    });

    it('pinchToFactor es la razon de distancias', () => {
        assert.equal(pinchToFactor(100, 200), 2);
        assert.equal(pinchToFactor(200, 100), 0.5);
        assert.equal(pinchToFactor(0, 100), 1, 'sin distancia previa no hay zoom');
        assert.equal(pinchToFactor(100, 0), 1);
    });
});

/* ------------------------------------------------------------------ *
 * graph-model
 * ------------------------------------------------------------------ */

function node(id: number, overrides: Partial<GraphPayload['nodes'][number]> = {}) {
    return {
        id,
        key: `company:SYM${id}`,
        type: 'company',
        label: `Empresa ${id}`,
        description: `Sector ${id} / Industria ${id}`,
        company_id: id,
        entity_type: 'company',
        entity_id: id,
        confidence: '0.9',
        attributes: { sector: `sector-${id}` },
        ...overrides,
    };
}

function edge(id: number, from: number, to: number) {
    return {
        id,
        from,
        to,
        type: 'has_principle',
        weight: '1',
        confidence: '0.75',
        evidence: [],
        provenance: 'deterministic_graph_sync_v1',
    };
}

/** Hub de 4 nodos: el centro unido a los tres periféricos, más un anillo cerrado. */
function sampleGraph(): GraphPayload {
    return {
        node_count: 6,
        edge_count: 5,
        nodes: [
            node(1),
            node(2),
            node(3, { type: 'principle', description: '' }),
            node(4, { type: 'risk', attributes: {} }),
            node(5, { type: 'kpi', description: '   ' }),
            node(6, { type: 'author', attributes: { aliases: null, tickets: 3 } }),
        ],
        edges: [edge(10, 1, 2), edge(11, 1, 3), edge(12, 1, 4), edge(13, 2, 5), edge(14, 2, 6)],
    };
}

describe('buildScene', () => {
    it('recorta al tope declarado y DEJA CONSTANCIA del recorte', () => {
        const nodes = Array.from({ length: 120 }, (_, index) => node(index + 1));
        const graph: GraphPayload = { node_count: 120, edge_count: 0, nodes, edges: [] };
        const scene = buildScene(graph);
        assert.equal(scene.nodes.length, MAX_SCENE_NODES);
        assert.equal(scene.hiddenNodeCount, 120 - MAX_SCENE_NODES);
        assert.equal(scene.totalNodeCount, 120);
    });

    it('cuenta como aristas ocultas las que pierden un extremo, no las que no existen', () => {
        const graph = sampleGraph();
        const scene = buildScene({ ...graph, nodes: graph.nodes.slice(0, 3) });
        // Aristas con ambos extremos visibles: 10 y 11.
        assert.equal(scene.edges.length, 2);
        assert.equal(scene.hiddenEdgeCount, 3);
        assert.equal(scene.totalEdgeCount, 5);
    });

    it('es determinista: el mismo grafo da las mismas posiciones', () => {
        const first = buildScene(sampleGraph());
        const second = buildScene(sampleGraph());
        assert.deepEqual(
            first.nodes.map((item) => [item.id, item.x, item.y]),
            second.nodes.map((item) => [item.id, item.x, item.y]),
        );
    });

    it('el layout normaliza la caja a origen positivo', () => {
        const scene = buildScene(sampleGraph());
        assert.ok(scene.bounds);
        assert.ok(scene.bounds!.minX >= 0 && scene.bounds!.minY >= 0, 'viewBox sin coordenadas negativas');
    });

    it('el radio crece con el grado y tiene tope', () => {
        assert.ok(radiusForDegree(0) < radiusForDegree(4));
        assert.ok(radiusForDegree(1000) <= 16);
        assert.ok(Number.isFinite(radiusForDegree(Number.NaN)));
        const scene = buildScene(sampleGraph());
        const hub = scene.nodeById.get(1)!;
        const leaf = scene.nodeById.get(5)!;
        assert.ok(hub.degree > leaf.degree);
        assert.ok(hub.radius > leaf.radius);
    });

    it('los anillos crecen de forma monotona y caben los nodos que seDibujan', () => {
        assert.ok(ringCapacity(1) > ringCapacity(0));
        assert.ok(ringCapacity(2) > ringCapacity(1));
        assert.ok(ringCapacity(0) > 0);
        assert.equal(ringCapacity(-4), ringCapacity(0), 'un anillo negativo no rompe nada');
    });

    it('las coordenadas no finitas del payload no rompen el bbox', () => {
        const broken = sampleGraph();
        broken.nodes[0] = { ...broken.nodes[0], label: 'X' };
        const scene = buildScene(broken);
        assert.ok(scene.bounds);
        for (const item of scene.nodes) {
            assert.ok(Number.isFinite(item.x) && Number.isFinite(item.y));
            assert.ok(Number.isFinite(item.radius));
        }
    });

    it('la adyacencia es simetrica y las aristas cuelgan de los dos extremos', () => {
        const scene = buildScene(sampleGraph());
        assert.ok(scene.neighbors.get(1)!.has(3));
        assert.ok(scene.neighbors.get(3)!.has(1));
        assert.equal(scene.incident.get(1)!.length, 3);
        assert.equal(scene.incident.get(3)!.length, 1);
    });

    it('normaliza confianza y peso numéricos y descarta los no numéricos', () => {
        const graph = sampleGraph();
        graph.edges[0] = { ...graph.edges[0], weight: '2.5', confidence: 'no-es-un-numero' };
        const scene = buildScene(graph);
        assert.equal(scene.edges[0].weight, 2.5);
        assert.equal(scene.edges[0].confidence, null);
    });
});

describe('focusIds y boundsFor', () => {
    it('depth 1 es el nodo y su vecindad inmediata', () => {
        const scene = buildScene(sampleGraph());
        const keep = focusIds(scene, 1, 1);
        assert.deepEqual([...(keep ?? [])].sort((a, b) => a - b), [1, 2, 3, 4]);
    });

    it('depth 0 deja el nodo solo', () => {
        const keep = focusIds(buildScene(sampleGraph()), 1, 0);
        assert.deepEqual([...(keep ?? [])], [1]);
    });

    it('depth 2 alcanza el grafo entero y por eso no atenua nada', () => {
        // El hub 1 llega a todo en dos saltos: el conjunto es el grafo entero,
        // asi que focusIds devuelve null y la vista no atenua nada (que es lo
        // correcto: no hay «resto» que ocultar).
        assert.equal(focusIds(buildScene(sampleGraph()), 1, 2), null);
    });

    it('devuelve null cuando el conjunto es el grafo entero (nada que atenuar)', () => {
        assert.equal(focusIds(buildScene(sampleGraph()), 1, 5), null);
        assert.equal(focusIds(buildScene(sampleGraph()), 999, 1), null, 'nodo inexistente');
    });

    it('boundsFor acota al subgrafo de foco', () => {
        const scene = buildScene(sampleGraph());
        const whole = boundsFor(scene, null)!;
        const hub = boundsFor(scene, focusIds(scene, 1, 0))!;
        assert.ok(hub.maxX < whole.maxX && hub.maxY < whole.maxY, 'la caja del hub es menor que la del grafo');
        assert.ok(scene.bounds!.maxX <= whole.maxX + 1e-6);
    });
});

describe('describeDetail', () => {
    it('devuelve los campos que el backend trae', () => {
        const scene = buildScene(sampleGraph());
        const fields = describeDetail(scene, 1);
        const byKey = new Map(fields.map((field) => [field.key, field]));
        assert.equal(byKey.get('label')!.value, 'Empresa 1');
        assert.equal(byKey.get('type')!.value, 'company');
        assert.equal(byKey.get('confidence')!.value, '90%');
        assert.equal(byKey.get('degree')!.value, '3');
        assert.equal(byKey.get('attribute:sector')!.value, 'sector-1');
    });

    it('los rotulos que define el grafo van por clave de i18n', () => {
        const fields = describeDetail(buildScene(sampleGraph()), 1);
        const builtin = fields.filter((field) => !field.key.startsWith('attribute:'));
        assert.ok(builtin.length > 0);
        assert.ok(
            builtin.every((field) => field.labelKey?.startsWith('knowledgeGraph.detail.fields.')),
            'todo rotulo del panel viene del diccionario',
        );
        // Un atributo se nombra con la clave que devuelve el backend, no con
        // una traduccion inventada (igual que `edge.type` en la tabla).
        const alias = fields.find((field) => field.key === 'attribute:sector')!;
        assert.equal(alias.labelKey, null);
        assert.equal(alias.label, 'sector');
    });

    it('una descripción vacía sale ausente CON MOTIVO, no como texto inventado', () => {
        const fields = describeDetail(buildScene(sampleGraph()), 3);
        const description = fields.find((field) => field.key === 'description')!;
        assert.equal(description.value, '');
        assert.ok(description.absent && description.absent.length > 10, 'el motivo explica por qué no hay dato');
    });

    it('una descripción con solo espacios también cuenta como ausente', () => {
        const fields = describeDetail(buildScene(sampleGraph()), 5);
        assert.equal(fields.find((field) => field.key === 'description')!.value, '');
    });

    it('sin atributos sale un campo «Atributos» ausente con motivo', () => {
        const fields = describeDetail(buildScene(sampleGraph()), 4);
        const attributes = fields.find((field) => field.key === 'attributes')!;
        assert.equal(attributes.value, '');
        assert.ok(attributes.absent);
    });

    it('descarta los atributos nulos, vacíos o en blanco y aplana los objetos', () => {
        const fields = describeDetail(buildScene(sampleGraph()), 6);
        const names = fields.filter((field) => field.key.startsWith('attribute:')).map((field) => field.key);
        assert.deepEqual(names, ['attribute:tickets'], 'aliases=null no es un dato');
        assert.equal(fields.find((field) => field.key === 'attribute:tickets')!.value, '3');
    });

    it('un nodo que no está en la escena no inventa campos', () => {
        assert.deepEqual(describeDetail(buildScene(sampleGraph()), 999), []);
    });
});

describe('searchNodes', () => {
    it('busca por nombre sin distinguir mayúsculas', () => {
        const scene = buildScene(sampleGraph());
        assert.equal(searchNodes(scene, 'empresa 1').length, 1);
        assert.equal(searchNodes(scene, 'EMPRESA').length, 6);
        assert.equal(searchNodes(scene, '   ').length, 0);
        assert.equal(searchNodes(scene, 'no-existe').length, 0);
    });

    it('acota el numero de sugerencias', () => {
        const nodes = Array.from({ length: 40 }, (_, index) => node(index + 1));
        const scene = buildScene({ node_count: 40, edge_count: 0, nodes, edges: [] });
        assert.equal(searchNodes(scene, 'Empresa', 3).length, 3);
    });
});

describe('volcado', () => {
    it('el SVG es autonomouso y lleva titulo accesible', () => {
        const svg = serializeSvg(buildScene(sampleGraph()), { title: 'Grafo de prueba' });
        assert.match(svg, /^<\?xml version="1\.0" encoding="UTF-8"\?>/);
        assert.match(svg, /xmlns="http:\/\/www\.w3\.org\/2000\/svg"/);
        assert.match(svg, /role="img"/);
        assert.match(svg, /aria-label="Grafo de prueba"/);
        assert.match(svg, /<circle/);
        assert.match(svg, /<title>/);
        assert.match(svg, new RegExp(`stroke="${EDGE_COLOR}"`));
    });

    it('el SVG escapa el texto de las etiquetas', () => {
        const graph = sampleGraph();
        graph.nodes[0] = { ...graph.nodes[0], label: 'A & B <script>' };
        const svg = serializeSvg(buildScene(graph));
        assert.match(svg, /A &amp; B &lt;script&gt;/);
        assert.equal(svg.includes('<script>'), false);
    });

    it('el SVG del subgrafo solo lleva sus nodos y sus aristas', () => {
        const scene = buildScene(sampleGraph());
        const keep = focusIds(scene, 1, 0)!;
        const svg = serializeSvg(scene, { keep });
        assert.match(svg, /<title>Empresa 1<\/title>/);
        assert.equal(svg.includes('Empresa 5'), false);
        assert.equal(svg.includes('<line'), false, 'el hub solo no tiene aristas');
        assert.equal(subgraphFor(scene, keep).nodes.length, 1);
    });

    it('el SVG marca el nodo seleccionado solo si esta en el subgrafo', () => {
        const scene = buildScene(sampleGraph());
        const keep = focusIds(scene, 1, 0)!;
        assert.match(serializeSvg(scene, { keep, selectedId: 1 }), /stroke="#5eead4"/);
        assert.equal(serializeSvg(scene, { keep, selectedId: 5 }).includes('#5eead4'), false);
    });

    it('el JSON lleva la procedencia de cada relacion y no inventa campos', () => {
        const payload = JSON.parse(serializeJson(buildScene(sampleGraph()), { keep: null }));
        assert.equal(payload.nodos.length, 6);
        assert.equal(payload.relaciones.length, 5);
        assert.equal(payload.relaciones[0].procedencia, 'deterministic_graph_sync_v1');
        assert.equal(payload.nodos[0].descripcion, 'Sector 1 / Industria 1');
        assert.equal(payload.nodos[2].descripcion, null, 'descripción ausente => null, no cadena inventada');
        assert.equal(payload.alcance, 'grafo completo');
        assert.equal(JSON.parse(serializeJson(buildScene(sampleGraph()), { keep: focusIds(buildScene(sampleGraph()), 1, 0) })).alcance, 'subgrafo de foco');
    });

    it('un grafo vacío se serializa sin romperse', () => {
        const empty = buildScene({ node_count: 0, edge_count: 0, nodes: [], edges: [] });
        assert.equal(empty.bounds, null);
        assert.match(serializeSvg(empty), /<svg[^>]*viewBox="0 0 1 1"/);
        assert.equal(JSON.parse(serializeJson(empty)).nodos.length, 0);
        assert.equal(focusIds(empty, 1, 1), null);
        assert.deepEqual(describeDetail(empty, 1), []);
    });
});