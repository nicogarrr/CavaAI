'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronRight } from 'lucide-react';
import { flattenNavItems, NAV_SECTIONS, type NavItem } from '@/lib/constants';

type Crumb = { href: string; label: string; navigable?: boolean };

/**
 * Migas derivadas de `NAV_SECTIONS`: la ruta se ancla al href mas largo que
 * coincida, y los segmentos sobrantes se anaden como migas propias. Asi
 * /research/MSFT/financial-terminal se lee "Analisis > Research > MSFT >
 * Terminal financiero" sin que ninguna pagina tenga que mantener su propia
 * jerarquia, y las rutas huerfanas del menu (que antes no existian en ningun
 * sitio) tienen contexto.
 */

/** Sub-rutas con nombre legible; el resto se muestra tal cual (ticker, screenId). */
const SUBROUTE_LABELS: Record<string, string> = {
  'financial-terminal': 'Terminal financiero',
  'driver-assumptions': 'Supuestos de drivers',
  'decision-lessons': 'Lecciones de decisiones',
  'management-credibility': 'Credibilidad de la directiva',
};

function buildCrumbs(pathname: string): Crumb[] {
  const items = flattenNavItems();
  const parentOf = new Map<string, NavItem>();
  const sectionOf = new Map<string, string>();
  for (const section of NAV_SECTIONS) {
    for (const item of section.items) {
      sectionOf.set(item.href, section.title);
      for (const node of [item, ...(item.children ?? [])]) {
        parentOf.set(node.href, item);
        if (!sectionOf.has(node.href)) sectionOf.set(node.href, section.title);
      }
    }
  }

  if (pathname === '/') return [{ href: '/', label: 'Inicio' }];

  // Ancla: el href mas largo que sea prefijo de la ruta.
  const anchor = items
    .filter((item) => item.href !== '/' && (pathname === item.href || pathname.startsWith(`${item.href}/`)))
    .sort((a, b) => b.href.length - a.href.length)[0];

  const crumbs: Crumb[] = [{ href: '/', label: 'Inicio' }];

  if (!anchor) return crumbs;

  const sectionTitle = sectionOf.get(anchor.href);
  if (sectionTitle && sectionTitle !== 'Principal') {
    // La seccion es un agrupador del menu, no una pagina: antes enlazaba a
    // `#Seccion`, un ancla sin destino en el documento (clic muerto). Se
    // muestra como texto, sin Link.
    crumbs.push({ href: `section:${sectionTitle}`, label: sectionTitle, navigable: false });
  }
  crumbs.push({ href: anchor.href, label: anchor.label });

  // Segmentos restantes: hijo declarado del nav, sub-ruta con nombre o el
  // propio identificador (ticker, screenId).
  const rest = pathname.slice(anchor.href.length).split('/').filter(Boolean);
  let parent = parentOf.get(anchor.href);
  rest.forEach((segment, index) => {
    const pathSoFar = `${anchor.href}/${rest.slice(0, index + 1).join('/')}`;
    const declared = parent?.children?.find((child) => child.href === pathSoFar);
    if (declared) {
      crumbs.push({ href: declared.href, label: declared.label });
      parent = declared;
      return;
    }
    crumbs.push({ href: pathSoFar, label: SUBROUTE_LABELS[segment] ?? segment });
  });

  return crumbs;
}

export default function Breadcrumbs() {
  const pathname = usePathname();
  const crumbs = buildCrumbs(pathname);
  if (crumbs.length < 2) return null;

  return (
    <nav aria-label="Ruta de navegación" className="mb-4 hidden md:block">
      <ol className="flex flex-wrap items-center gap-1 text-sm text-gray-500">
        {crumbs.map((crumb, index) => {
          const isLast = index === crumbs.length - 1;
          return (
            <li className="flex items-center gap-1" key={crumb.href}>
              {index > 0 && <ChevronRight aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />}
              {isLast ? (
                <span aria-current="page" className="max-w-[24ch] truncate text-gray-300">{crumb.label}</span>
              ) : crumb.navigable === false ? (
                <span className="max-w-[24ch] truncate">{crumb.label}</span>
              ) : (
                <Link href={crumb.href} className="max-w-[24ch] truncate hover:text-teal-300">{crumb.label}</Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
