'use client'

import Link from 'next/link'
import {usePathname} from 'next/navigation'
import {isNavItemActive, NAV_SECTIONS, showsNavSectionTitle, type NavItem} from '@/lib/constants'

/**
 * Version movil del menu. Comparte arbol, reglas de estado activo y titulos con
 * `components/layout/Sidebar.tsx`; lo unico que cambia son las alturas tactiles
 * (min-h-11) y que aqui no hay version plegable.
 */
const NavItems = () => {
    const pathname = usePathname()

    return (
        <ul className="flex max-w-full flex-col p-2 text-sm font-medium">
            {NAV_SECTIONS.map((section) => (
                <li key={section.title}>
                    {showsNavSectionTitle(section) && (
                        <p className="px-1 pb-1 pt-4 text-xs font-semibold uppercase tracking-wide text-gray-400">
                            {section.title}
                        </p>
                    )}
                    <ul className="flex flex-col gap-1">
                        {section.items.map((item) => (
                            <li className="shrink-0" key={item.href}>
                                <ItemLink item={item} pathname={pathname} />
                            </li>
                        ))}
                    </ul>
                </li>
            ))}
        </ul>
    )
}

function ItemLink({item, pathname}: {item: NavItem; pathname: string}) {
    const active = isNavItemActive(pathname, item.href)
    const branchActive = active || (item.children ?? []).some((child) => isNavItemActive(pathname, child.href))

    return (
        <>
            <Link
                href={item.href}
                prefetch
                aria-current={active ? 'page' : undefined}
                className={classes(branchActive)}
            >
                {item.icon && <item.icon aria-hidden="true" className="h-4 w-4 shrink-0" />}
                <span className="truncate">{item.label}</span>
            </Link>
            {item.children && (
                <ul className="mt-1 flex flex-col gap-1 border-l border-gray-700/50 pl-3">
                    {item.children.map((child) => (
                        <li className="shrink-0" key={child.href}>
                            <Link
                                href={child.href}
                                prefetch
                                aria-current={isNavItemActive(pathname, child.href) ? 'page' : undefined}
                                className={classes(isNavItemActive(pathname, child.href), 'text-base')}
                            >
                                <span className="truncate">{child.label}</span>
                            </Link>
                        </li>
                    ))}
                </ul>
            )}
        </>
    )
}

/** Mismo tratamiento activo que en desktop: barra teal, no solo un fondo. */
function classes(active: boolean, size = 'text-base') {
    return [
        'relative flex min-h-11 items-center gap-2 rounded-lg px-2 py-2 transition-colors',
        size,
        active
            ? 'bg-gray-800/70 text-gray-100 before:absolute before:inset-y-1.5 before:left-0 before:w-0.5 before:rounded-full before:bg-teal-400'
            : 'text-gray-400 hover:bg-gray-800/70 hover:text-teal-300',
    ].join(' ')
}

export default NavItems
