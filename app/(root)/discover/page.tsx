import Link from 'next/link';
import { ArrowUpRight, Filter, Landmark, LineChart, Sparkles, TrendingUp, Users } from 'lucide-react';
const tools=[
 {href:'/screener',name:'Mercado',description:'Explora empresas por sector y tamaño.',icon:LineChart},
 {href:'/screeners',name:'Filtros',description:'Busca con métricas y filtros guardados.',icon:Filter},
 {href:'/inversores',name:'Inversores',description:'Carteras declaradas y cambios en los filings.',icon:Landmark},
 {href:'/insider',name:'Insider',description:'Compras declaradas por directivos en Form 4.',icon:Users},
 {href:'/propicks',name:'Selecciones',description:'Ranking, reglas de selección y backtest.',icon:Sparkles},
 {href:'/movers',name:'Movimientos de mercado',description:'Subidas, bajadas y actividad por sesión.',icon:TrendingUp},
];
export default function Discover(){return <main id="content" className="mx-auto max-w-6xl"><header className="mb-8"><p className="mb-2 text-xs font-semibold uppercase tracking-widest text-teal-400">Empresas y señales</p><h1 className="text-3xl font-semibold text-gray-100">Descubrir</h1></header><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{tools.map(({href,name,description,icon:Icon})=><Link key={href} href={href} className="group rounded-xl border border-gray-800 bg-gray-900/40 p-5 transition-colors hover:border-teal-400/40 hover:bg-gray-900"><div className="mb-5 flex items-center justify-between"><Icon aria-hidden="true" className="h-5 w-5 text-teal-400"/><ArrowUpRight aria-hidden="true" className="h-4 w-4 text-gray-600 group-hover:text-teal-300"/></div><h2 className="text-lg font-medium text-gray-100">{name}</h2><p className="mt-2 text-sm leading-relaxed text-gray-400">{description}</p></Link>)}</div></main>}
