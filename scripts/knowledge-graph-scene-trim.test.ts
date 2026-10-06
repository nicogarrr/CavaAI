/**
 * D2b/honestidad: el recorte del grafo y su volcado no pueden mentir.
 *
 * Dos regresiones concretas, ambas invisibles en la UI de un vistazo:
 *
 *  1. RECORTE POR ID. `buildScene` recortaba con `nodes.slice(0, max)` sobre
 *     el orden de id del backend. Con un hub de grado 79 al final del payload
 *     el recorte lo excluía: el grafo dibujado quedaba en 80 nodos casi todos
 *     de grado 0-2, el grado máximo dibujado caía a 2 y el radial resultante
 *     era indistinguible de un grafo plano. El recorte tiene que elegir por
 *     GRADO (los más conectados primero) y decirlo.
 *
 *  2. VOLCADO RECORTADO. `truncatedHint` promete «exporta el JSON para ver el
 *     subgrafo completo» pero el volcado serializaba la escena YA recortada a
 *     MAX_SCENE_NODES: los nodos y aristas ocultos nunca llegaban al fichero
 *     que los prometía. El volcado sale del payload, sin el recorte del dibujo.
 *
 * Ejecucion: node --experimental-strip-types --test scripts/knowledge-graph-scene-trim.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import {
    buildScene,
    exportFullGraph,
    MAX_SCENE_NODES,
    type GraphPayload,
    // @ts-expect-error TS5097: la extension .ts explicita la exige node --experimental-strip-types en runtime.
} from '../lib/knowledge-graph/graph-model.ts';

function node(id: number): GraphPayload['nodes'][number] {
    return {
        id,
        key: `company:SYM${id}`,
        type: 'company',
        label: `Empresa ${id}`,
        description: `Sector ${id}`,
        company_id: id,
        entity_type: 'company',
        entity_id: id,
        confidence: '0.9',
        attributes: {},
    };
}

function edge(id: number, from: number, to: number): GraphPayload['edges'][number] {
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

/**
 * El peor caso reproducido: 120 nodos, un hub de grado 79 colocado EL ULTIMO
 * del array y el resto de aristas formando una cadena corta entre los primeros
 * ids (lo que engordaba el grado de los nodos que el recorte por id sí veía).
 */
function hubAlFinal(): GraphPayload {
    const nodes = Array.from({ length: 120 }, (_, index) => node(index + 1));
    const edges: GraphPayload['edges'] = [];
    // Hub (id 120) unido a los nodos 1..79: 79 aristas; el hub va el ULTIMO
    // del array y los nodos 80..119 se quedan sueltos (grado 0). El recorte
    // por id dibujaba esos sueltos y excluia al hub.
    for (let target = 1; target <= 79; target += 1) {
        edges.push(edge(edges.length + 1, 120, target));
    }
    return { node_count: 120, edge_count: edges.length, nodes, edges };
}

describe('buildScene recorta por grado, no por orden de id', () => {
    it('el hub al final del payload sobrevive al recorte', () => {
        const scene = buildScene(hubAlFinal());
        assert.ok(scene.nodeById.has(120), 'el nodo mas conectado no puede caerse del dibujo');
        assert.ok(scene.nodes.length <= MAX_SCENE_NODES);
    });

    it('el grado maximo dibujado no se desploma al recortar', () => {
        const scene = buildScene(hubAlFinal());
        const maxDrawnDegree = Math.max(...scene.nodes.map((item) => item.degree));
        assert.ok(maxDrawnDegree >= 79, `el hub deberia dibujarse con sus 79 aristas, grado maximo ${maxDrawnDegree}`);
    });

    it('lo que se recorta son los MENOS conectados', () => {
        const graph = hubAlFinal();
        const scene = buildScene(graph);
        const keptIds = new Set(scene.nodes.map((item) => item.id));
        const dropped = graph.nodes.filter((item) => !keptIds.has(item.id));
        assert.ok(dropped.length > 0, 'el caso tiene que recortar algo para probar nada');
        // Invariante del orden de corte: grado total descendente, id ascendente.
        const total = new Map(graph.nodes.map((item) => [item.id, 0]));
        for (const item of graph.edges) {
            total.set(item.from, (total.get(item.from) ?? 0) + 1);
            total.set(item.to, (total.get(item.to) ?? 0) + 1);
        }
        for (const lost of dropped) {
            for (const drawn of scene.nodes) {
                const worseDegree = (total.get(lost.id) ?? 0) < (total.get(drawn.id) ?? 0);
                const sameDegreeLaterId = (total.get(lost.id) ?? 0) === (total.get(drawn.id) ?? 0) && lost.id > drawn.id;
                assert.ok(worseDegree || sameDegreeLaterId, `nodo ${lost.id} recortado antes que ${drawn.id}`);
            }
        }
    });

    it('es determinista: dos construcciones recortan lo mismo', () => {
        const first = buildScene(hubAlFinal());
        const second = buildScene(hubAlFinal());
        assert.deepEqual(first.nodes.map((item) => item.id), second.nodes.map((item) => item.id));
    });
});

describe('exportFullGraph no arrastra el recorte del dibujo', () => {
    it('el JSON contiene TODOS los nodos y aristas cargados', () => {
        const graph = hubAlFinal();
        const payload = JSON.parse(exportFullGraph(graph, 'json'));
        assert.equal(payload.nodos.length, 120, 'el volcado no puede perder los nodos que el dibujo oculta');
        assert.equal(payload.relaciones.length, graph.edges.length);
        assert.equal(payload.alcance, 'grafo completo');
    });

    it('el hub oculto por el dibujo llega al fichero', () => {
        const graph = hubAlFinal();
        const scene = buildScene(graph);
        const payload = JSON.parse(exportFullGraph(graph, 'json'));
        const labels = payload.nodos.map((item: { etiqueta: string }) => item.etiqueta);
        for (const item of scene.nodes) {
            assert.ok(labels.includes(item.label), `el dibujo muestra ${item.label} y el volcado no`);
        }
        assert.ok(labels.includes('Empresa 120'), 'el hub debe estar en el volcado aunque sea el ultimo del payload');
    });

    it('el SVG tambien sale sin el recorte y con el nodo seleccionado marcado', () => {
        const graph = hubAlFinal();
        const svg = exportFullGraph(graph, 'svg', { selectedId: 120 });
        assert.ok(svg.includes('Empresa 120'));
        assert.ok(svg.includes('Empresa 1'));
        assert.ok(svg.includes('stroke="#5eead4"'), 'el nodo seleccionado se marca en el volcado');
    });

    it('sin recorte posible (grafo pequeno) el volcado es identico al dibujo', () => {
        const graph: GraphPayload = { node_count: 3, edge_count: 2, nodes: [node(1), node(2), node(3)], edges: [edge(1, 1, 2), edge(2, 2, 3)] };
        const payload = JSON.parse(exportFullGraph(graph, 'json'));
        assert.equal(payload.nodos.length, 3);
        assert.equal(payload.relaciones.length, 2);
    });
});
