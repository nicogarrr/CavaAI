import type { Metadata } from 'next';
import Link from 'next/link';
import { GitBranch, RefreshCcw } from 'lucide-react';

import { MutationForm } from '@/components/forms/MutationForm';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { PageHeader } from '@/components/ui/page-header';
import { Stat } from '@/components/ui/stat';
import { getKnowledgeGraph, getKnowledgeNeighborhood, syncKnowledgeGraph } from '@/lib/actions/research-tools.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
  title: 'Grafo de conocimiento',
  description:
    'Enlaces deterministas entre autores, principios, empresas, KPIs, riesgos, decisiones, lecciones y conceptos, con su procedencia.',
};

const colors: Record<string, string> = { company: '#14b8a6', principle: '#8b5cf6', author: '#a78bfa', decision: '#3b82f6', decision_lesson: '#22c55e', kpi: '#f59e0b', risk: '#ef4444', concept: '#ec4899', case_study: '#06b6d4' };

export default async function KnowledgeGraphPage({ searchParams }: { searchParams: Promise<{ node_types?: string; ticker?: string; limit?: string; node?: string; depth?: string }> }) {
  const query = await searchParams;
  const selectedNode = Number(query.node) || null;
  const graph = selectedNode
    ? await getKnowledgeNeighborhood(selectedNode, Number(query.depth) || 2)
    : await getKnowledgeGraph({ nodeTypes: query.node_types, ticker: query.ticker, limit: Number(query.limit) || 120 });
  const visibleNodes = graph.nodes.slice(0, 80);
  const visibleIds = new Set(visibleNodes.map((node) => node.id));
  const width = 1100, height = 620, radius = 250;
  const positions = new Map(visibleNodes.map((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(1, visibleNodes.length) - Math.PI / 2;
    const ring = radius * (0.58 + 0.42 * ((index % 3) / 2));
    return [node.id, { x: width / 2 + Math.cos(angle) * ring, y: height / 2 + Math.sin(angle) * ring }] as const;
  }));
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
  const typeCounts = Object.entries(graph.nodes.reduce<Record<string, number>>((acc, node) => ({ ...acc, [node.type]: (acc[node.type] ?? 0) + 1 }), {})).sort((a, b) => b[1] - a[1]);
    return <main id="content" tabIndex={-1} className="mx-auto flex w-full min-w-0 max-w-[1500px] flex-col gap-6 overflow-x-clip"><PageHeader actions={<MutationForm action={syncKnowledgeGraph} successMessage="Grafo sincronizado"><Button className="h-11 w-full md:w-auto" type="submit"><RefreshCcw aria-hidden="true" className="h-4 w-4" />Sincronizar grafo</Button></MutationForm>} description="Explora enlaces deterministas entre autores, principios, empresas, KPIs, riesgos, decisiones, lecciones y conceptos." kicker="Research conectado" title="Grafo de conocimiento" />
    {selectedNode ? <div className="flex flex-wrap items-center gap-3 rounded-xl border border-teal-900/50 bg-teal-950/10 p-4"><span className="text-sm text-gray-300">Entorno del nodo #{selectedNode}</span><Button asChild className="ml-auto" size="sm" variant="outline"><Link href="/knowledge-graph">Grafo completo</Link></Button></div> : <form className="min-w-0 rounded-xl border border-gray-800 bg-surface-1 p-4" method="get"><div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_160px_120px_auto]"><Input className="h-11 w-full" defaultValue={query.node_types} name="node_types" placeholder="Tipos de nodo, separados por comas" /><Input className="h-11 w-full" defaultValue={query.ticker} name="ticker" placeholder="Ticker" /><Input className="h-11 w-full" defaultValue={query.limit ?? '120'} max="500" min="1" name="limit" type="number" /><Button className="h-11 w-full md:w-auto" type="submit">Filtrar</Button></div></form>}
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-6"><Stat label="Nodos" value={graph.node_count} /><Stat label="Aristas" value={graph.edge_count} />{typeCounts.slice(0, 4).map(([type, count]) => <Stat key={type} label={type.replaceAll('_', ' ')} value={<span style={{ color: colors[type] ?? '#d1d5db' }}>{count}</span>} />)}</section>
    <section className="w-full min-w-0 overflow-hidden rounded-xl border border-gray-800 bg-surface-0 p-3">
<div className="mb-2 flex flex-wrap gap-2">{typeCounts.map(([type]) => <Badge key={type} variant="outline"><span className="mr-2 inline-block h-2 w-2 rounded-full" style={{ backgroundColor: colors[type] ?? '#9ca3af' }} />{type.replaceAll('_', ' ')}</Badge>)}</div>{visibleNodes.length ? <div className="w-full overflow-hidden"><svg aria-label="Visualización del grafo de conocimiento" className="h-auto w-full" height={height} style={{ height: 'auto' }} viewBox={`0 0 ${width} ${height}`} width="100%"><g>{graph.edges.filter((edge) => visibleIds.has(edge.from) && visibleIds.has(edge.to)).map((edge) => { const from = positions.get(edge.from)!, to = positions.get(edge.to)!; return <line key={edge.id} x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke="#374151" strokeOpacity="0.65" strokeWidth={Math.max(1, Number(edge.weight))} />; })}</g><g>{visibleNodes.map((node) => { const point = positions.get(node.id)!; return <g key={node.id}><Link href={`/knowledge-graph?node=${node.id}&depth=2`}><circle cx={point.x} cy={point.y} fill={colors[node.type] ?? '#9ca3af'} r={selectedNode === node.id ? 10 : 7}><title>{node.label}</title></circle></Link>{visibleNodes.length <= 45 ? <text fill="#9ca3af" fontSize="10" x={point.x + 10} y={point.y + 4}>{node.label.slice(0, 28)}</text> : null}</g>; })}</g></svg></div> : <div className="p-10 text-center text-sm text-gray-500">Sincroniza el grafo para crear nodos y relaciones.</div>}</section>
        <section className="min-w-0 rounded-xl border border-gray-800 bg-surface-1 p-4 sm:p-5"><div className="mb-4 flex items-center gap-2"><GitBranch aria-hidden="true" className="h-5 w-5 text-teal-300" /><h2 className="font-semibold text-gray-100">Relaciones</h2></div>
<div aria-label="Relaciones del grafo" className="hidden overflow-x-auto md:block" role="region" tabIndex={0}><table className="w-full min-w-[640px] text-left text-sm"><caption className="sr-only">Relaciones del grafo de conocimiento: nodo de origen, tipo de relación, nodo de destino, confianza y procedencia</caption><thead className="text-xs uppercase text-gray-500"><tr><th className="border-b border-gray-800 py-2" scope="col">Desde</th><th className="border-b border-gray-800 py-2" scope="col">Relación</th><th className="border-b border-gray-800 py-2" scope="col">Hasta</th><th className="border-b border-gray-800 py-2 text-right" scope="col">Confianza</th><th className="border-b border-gray-800 py-2" scope="col">Procedencia</th></tr></thead><tbody>{graph.edges.map((edge) => <tr className="border-b border-gray-900" key={edge.id}><th className="py-3 text-left text-sm font-normal text-gray-300" scope="row">{nodeById.get(edge.from)?.label ?? `Nodo ${edge.from}`}</th><td className="py-3"><Badge variant="outline">{edge.type}</Badge></td><td className="py-3 text-gray-300">{nodeById.get(edge.to)?.label ?? `Nodo ${edge.to}`}</td><td className="py-3 text-right text-gray-400">{(Number(edge.confidence) * 100).toFixed(0)}%</td><td className="py-3 text-xs text-gray-500">{edge.provenance}</td></tr>)}{!graph.edges.length ? <tr><td className="py-5 text-gray-500" colSpan={5}>Ninguna relación coincide con el ámbito actual.</td></tr> : null}</tbody></table></div><div className="grid grid-cols-1 gap-3 md:hidden">{!graph.edges.length ? <p className="text-sm text-gray-500">Ninguna relación coincide con el ámbito actual.</p> : null}{graph.edges.slice(0, 30).map((edge) => <article className="min-w-0 rounded-lg border border-gray-800 bg-black/30 p-4 break-words" key={edge.id}><div className="text-sm font-medium text-gray-200">{nodeById.get(edge.from)?.label ?? `Nodo ${edge.from}`}</div><div className="mt-2 flex flex-wrap items-center gap-2"><Badge variant="outline">{edge.type}</Badge><span className="text-xs text-gray-500">→</span><span className="text-sm text-gray-300">{nodeById.get(edge.to)?.label ?? `Nodo ${edge.to}`}</span></div><div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500"><span>Confianza {(Number(edge.confidence) * 100).toFixed(0)}%</span><span>{edge.provenance}</span></div></article>)}{graph.edges.length > 30 ? <p className="text-xs text-gray-500">Mostrando 30 de {graph.edges.length} relaciones — filtra para acotar el ámbito.</p> : null}</div></section>
  </main>;
}
