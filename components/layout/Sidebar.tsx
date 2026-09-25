'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronsLeft, ChevronsRight, CircleHelp, Settings, Target } from 'lucide-react';
import { isNavItemActive, NAV_SECTIONS, showsNavSectionTitle, type NavItem } from '@/lib/constants';

export const SIDEBAR_COLLAPSED_COOKIE = 'cavaai:sidebar-collapsed';

/**
 * Navegacion de escritorio. Complementa a `components/MobileNav.tsx`, que usa
 * el mismo arbol de `NAV_SECTIONS`: los breakpoints son los mismos (`md`) para
 * que entre 640px y 767px no quede ninguna ventana sin navegacion primaria.
 *
 * Alturas y anchuras vienen de --shell-top / --sidebar-w (globals.css). El
 * aside se ancla a `top-0` con `h-dvh` y reserva el alto de la zona pegajosa
 * con `pt`: asi el borde superior nunca queda escondido bajo el header, y lo
 * mismo vale cuando el aviso de "sin conexion" aniade su propia altura.
 */
export default function Sidebar({ collapsed: initiallyCollapsed }: { collapsed: boolean }) {
    const pathname = usePathname();
    const [collapsed, setCollapsed] = useState(initiallyCollapsed);

    const toggle = () => {
        setCollapsed((prev) => {
            const next = !prev;
            document.cookie = `${SIDEBAR_COLLAPSED_COOKIE}=${next ? '1' : '0'};path=/;max-age=31536000;samesite=lax`;
            return next;
        });
    };

    return (
        <aside
            data-collapsed={collapsed || undefined}
            className="sticky top-0 z-10 hidden h-dvh shrink-0 flex-col border-r border-gray-700/50 bg-gray-900 pt-[var(--shell-top)] transition-[width] duration-200 md:flex data-[collapsed]:w-[var(--sidebar-w-collapsed)] w-[var(--sidebar-w)]"
        >
            <button
                onClick={toggle}
                title={collapsed ? 'Expandir menú' : 'Plegar menú'}
                aria-label={collapsed ? 'Expandir menú' : 'Plegar menú'}
                aria-expanded={!collapsed}
                className="m-2 flex h-9 w-fit items-center justify-center rounded-lg text-gray-300 hover:bg-gray-800 hover:text-teal-300"
            >
                {collapsed ? <ChevronsRight aria-hidden="true" className="h-5 w-5" /> : <ChevronsLeft aria-hidden="true" className="h-5 w-5" />}
            </button>

            <nav className="scrollbar-hide-default flex-1 overflow-y-auto px-2 pb-4" aria-label="Navegación principal">
                <ul className="flex flex-col">
                    {NAV_SECTIONS.map((section) => {
                        const showTitle = showsNavSectionTitle(section);
                        return (
                            <li key={section.title}>
                                {showTitle && (
                                    collapsed ? (
                                        <div className="mx-2 my-3 border-t border-gray-700/50" aria-hidden="true" />
                                    ) : (
                                        <p className="px-3 pb-1 pt-4 text-xs font-semibold uppercase tracking-wide text-gray-500">
                                            {section.title}
                                        </p>
                                    )
                                )}
                                <ul className="flex flex-col gap-1">
                                    {section.items.map((item) => (
                                        <li key={item.href}>
                                            <NavLink item={item} pathname={pathname} collapsed={collapsed} />
                                        </li>
                                    ))}
                                </ul>
                            </li>
                        );
                    })}
                </ul>
            </nav>

            {/* Pie del menu: destinos que no caben en el arbol pero deben ser
                alcanzables sin conocer la URL. Antes /help no tenia entrada. */}
            <div className="border-t border-gray-700/50 p-2">
                <ul className="flex flex-col gap-1">
                    <li>
                        <FooterLink href="/plan" icon={Target} label="Mi plan" pathname={pathname} collapsed={collapsed} />
                    </li>
                    <li>
                        <FooterLink href="/security" icon={Settings} label="Seguridad" pathname={pathname} collapsed={collapsed} />
                    </li>
                    <li>
                        <FooterLink href="/help" icon={CircleHelp} label="Ayuda" pathname={pathname} collapsed={collapsed} />
                    </li>
                </ul>
            </div>
        </aside>
    );
}

function NavLink({ item, pathname, collapsed }: { item: NavItem; pathname: string; collapsed: boolean }) {
    const active = isNavItemActive(pathname, item.href);
    // Un padre se ilumina cuando la ruta cae en un hijo suyo, para que la
    // rama "Research" siga visible dentro de /research/news.
    const branchActive = active || (item.children ?? []).some((child) => isNavItemActive(pathname, child.href));

    return (
        <>
            <Link
                href={item.href}
                prefetch
                title={collapsed ? item.label : undefined}
                aria-current={active ? 'page' : undefined}
                className={linkClasses(branchActive, collapsed)}
            >
                {item.icon && <item.icon aria-hidden="true" className="h-4 w-4 shrink-0" />}
                {!collapsed && <span className="truncate">{item.label}</span>}
            </Link>
            {!collapsed && item.children && (
                <ul className="mt-1 flex flex-col gap-1 border-l border-gray-700/50 pl-3">
                    {item.children.map((child) => (
                        <li key={child.href}>
                            <Link
                                href={child.href}
                                prefetch
                                aria-current={isNavItemActive(pathname, child.href) ? 'page' : undefined}
                                className={linkClasses(isNavItemActive(pathname, child.href), false, 'text-sm')}
                            >
                                <span className="truncate">{child.label}</span>
                            </Link>
                        </li>
                    ))}
                </ul>
            )}
        </>
    );
}

function FooterLink({
    href,
    icon: Icon,
    label,
    pathname,
    collapsed,
}: {
    href: string;
    icon: typeof Target;
    label: string;
    pathname: string;
    collapsed: boolean;
}) {
    return (
        <Link
            href={href}
            title={collapsed ? label : undefined}
            aria-current={isNavItemActive(pathname, href) ? 'page' : undefined}
            className={linkClasses(isNavItemActive(pathname, href), collapsed, 'text-sm')}
        >
            <Icon aria-hidden="true" className="h-4 w-4 shrink-0" />
            {!collapsed && <span className="truncate">{label}</span>}
        </Link>
    );
}

/**
 * La barra teal del item activo se dibuja con un pseudo-elemento en vez de con
 * `border-l-2`: un borde real cambia el ancho de la caja al alternar estados
 * y hace que el redondeo se corte en la esquina.
 */
function linkClasses(active: boolean, collapsed: boolean, extra = 'text-sm') {
    return [
        'relative flex items-center gap-3 rounded-lg px-3 py-2 transition-colors',
        extra,
        collapsed ? 'justify-center' : '',
        active
            ? 'bg-gray-800 text-gray-100 before:absolute before:inset-y-1.5 before:left-0 before:w-0.5 before:rounded-full before:bg-teal-400'
            : 'text-gray-400 hover:bg-gray-800 hover:text-teal-300',
    ].join(' ');
}
