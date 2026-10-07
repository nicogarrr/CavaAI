'use client';
import Link from 'next/link';
import {usePathname} from 'next/navigation';
import {sectionForRoute} from '@/lib/constants';
const groups: Record<string, readonly [string,string][]> = {
 '/portfolio': [['/portfolio','Posiciones e historial'],['/portfolio/intelligence','Rendimiento'],['/risk','Riesgo'],['/plan','Plan'],['/taxes','Fiscal'],['/corporate-actions','Eventos'],['/export','Exportar']],
 '/research': [['/research','Empresas'],['/research/assistant','Asistente'],['/research/news','Noticias'],['/research/sources','Fuentes']],
 '/discover': [['/screener','Mercado'],['/screeners','Filtros'],['/movers','Movimientos'],['/insider','Insider'],['/inversores','Inversores'],['/ownership','Datos 13F'],['/propicks','Selecciones']],
 '/knowledge': [['/knowledge','Documentos y principios'],['/inversores/canales','Canales'],['/knowledge-graph','Grafo avanzado'],['/export','Exportar']],
 '/watchlist': [['/alerts','Reglas y avisos']],
};
export default function SectionNav(){
 const pathname=usePathname();
 const section=sectionForRoute(pathname);
 const items=section?groups[section]:null;
 if(!items || pathname === '/discover')return null;
 return <nav aria-label="Herramientas de la sección" className="mb-6 flex flex-wrap gap-1.5 border-b border-gray-800 pb-3">{items.map(([href,name])=>{
  const active=href===pathname;
  return <Link key={href} href={href} aria-current={active?'page':undefined} className={`inline-flex min-h-11 items-center rounded-lg px-3 py-2 text-sm transition-colors ${active?'bg-teal-400/10 text-teal-300':'text-gray-400 hover:bg-gray-800 hover:text-gray-100'}`}>{name}</Link>;
 })}</nav>;
}
