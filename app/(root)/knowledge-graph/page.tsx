import Link from 'next/link';
import { GitBranch, RefreshCcw } from 'lucide-react';

import { MutationForm } from '@/components/forms/MutationForm';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { getKnowledgeGraph, getKnowledgeNeighborhood, syncKnowledgeGraph } from '@/lib/actions/research-tools.actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

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
  return <main className="mx-auto flex max-w-[1500px] flex-col gap-6"><header className="flex flex-col gap-4 border-b border-gray-800 pb-5 md:flex-row md:items-end"><div><p className="text-sm font-semibold uppercase text-teal-300">Connected research</p><h1 className="mt-1 text-3xl font-bold text-gray-100">Knowledge Graph</h1><p className="mt-2 text-sm text-gray-400">Explore deterministic links between authors, principles, companies, KPIs, risks, decisions, lessons and concepts.</p></div><MutationForm action={syncKnowledgeGraph} className="md:ml-auto" successMessage="Graph synchronized"><Button type="submit"><RefreshCcw className="h-4 w-4" />Sync graph</Button></MutationForm></header>
    {selectedNode ? <div className="flex items-center gap-3 rounded-xl border border-teal-900/50 bg-teal-950/10 p-4"><span className="text-sm text-gray-300">Neighborhood rooted at node #{selectedNode}</span><Button asChild className="ml-auto" size="sm" variant="outline"><Link href="/knowledge-graph">Full graph</Link></Button></div> : <form className="rounded-xl border border-gray-800 bg-[#101010] p-4" method="get"><div className="grid gap-3 md:grid-cols-[1fr_160px_120px_auto]"><Input defaultValue={query.node_types} name="node_types" placeholder="Node types, comma separated" /><Input defaultValue={query.ticker} name="ticker" placeholder="Ticker" /><Input defaultValue={query.limit ?? '120'} max="500" min="1" name="limit" type="number" /><Button type="submit">Filter</Button></div></form>}
    <section className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6"><div className="rounded-xl border border-gray-800 bg-[#101010] p-4"><div className="text-xs uppercase text-gray-500">Nodes</div><div className="mt-2 text-2xl font-semibold text-gray-100">{graph.node_count}</div></div><div className="rounded-xl border border-gray-800 bg-[#101010] p-4"><div className="text-xs uppercase text-gray-500">Edges</div><div className="mt-2 text-2xl font-semibold text-gray-100">{graph.edge_count}</div></div>{typeCounts.slice(0, 4).map(([type, count]) => <div className="rounded-xl border border-gray-800 bg-[#101010] p-4" key={type}><div className="text-xs uppercase text-gray-500">{type.replaceAll('_', ' ')}</div><div className="mt-2 text-2xl font-semibold" style={{ color: colors[type] ?? '#d1d5db' }}>{count}</div></div>)}</section>
    <section className="overflow-hidden rounded-xl border border-gray-800 bg-[#080808] p-3"><div className="mb-2 flex flex-wrap gap-2">{typeCounts.map(([type]) => <Badge key={type} variant="outline"><span className="mr-2 inline-block h-2 w-2 rounded-full" style={{ backgroundColor: colors[type] ?? '#9ca3af' }} />{type.replaceAll('_', ' ')}</Badge>)}</div>{visibleNodes.length ? <div className="overflow-x-auto"><svg aria-label="Knowledge graph visualization" className="min-w-[1100px]" height={height} viewBox={`0 0 ${width} ${height}`} width="100%"><g>{graph.edges.filter((edge) => visibleIds.has(edge.from) && visibleIds.has(edge.to)).map((edge) => { const from = positions.get(edge.from)!, to = positions.get(edge.to)!; return <line key={edge.id} x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke="#374151" strokeOpacity="0.65" strokeWidth={Math.max(1, Number(edge.weight))} />; })}</g><g>{visibleNodes.map((node) => { const point = positions.get(node.id)!; return <g key={node.id}><Link href={`/knowledge-graph?node=${node.id}&depth=2`}><circle cx={point.x} cy={point.y} fill={colors[node.type] ?? '#9ca3af'} r={selectedNode === node.id ? 10 : 7}><title>{node.label}</title></circle></Link>{visibleNodes.length <= 45 ? <text fill="#9ca3af" fontSize="10" x={point.x + 10} y={point.y + 4}>{node.label.slice(0, 28)}</text> : null}</g>; })}</g></svg></div> : <div className="p-10 text-center text-sm text-gray-500">Synchronize the graph to create nodes and relationships.</div>}</section>
    <section className="rounded-xl border border-gray-800 bg-[#101010] p-5"><div className="mb-4 flex items-center gap-2"><GitBranch className="h-5 w-5 text-teal-300" /><h2 className="font-semibold text-gray-100">Relationships</h2></div><div className="overflow-x-auto"><table className="w-full min-w-[900px] text-left text-sm"><thead className="text-xs uppercase text-gray-500"><tr><th className="border-b border-gray-800 py-2">From</th><th className="border-b border-gray-800 py-2">Relationship</th><th className="border-b border-gray-800 py-2">To</th><th className="border-b border-gray-800 py-2 text-right">Confidence</th><th className="border-b border-gray-800 py-2">Provenance</th></tr></thead><tbody>{graph.edges.map((edge) => <tr className="border-b border-gray-900" key={edge.id}><td className="py-3 text-gray-300">{nodeById.get(edge.from)?.label ?? `Node ${edge.from}`}</td><td className="py-3"><Badge variant="outline">{edge.type}</Badge></td><td className="py-3 text-gray-300">{nodeById.get(edge.to)?.label ?? `Node ${edge.to}`}</td><td className="py-3 text-right text-gray-400">{(Number(edge.confidence) * 100).toFixed(0)}%</td><td className="py-3 text-xs text-gray-500">{edge.provenance}</td></tr>)}{!graph.edges.length ? <tr><td className="py-5 text-gray-500" colSpan={5}>No relationships match the current scope.</td></tr> : null}</tbody></table></div></section>
  </main>;
}
