'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronsLeft, ChevronsRight } from 'lucide-react';
import { NAV_ITEMS } from '@/lib/constants';

const STORAGE_KEY = 'cavaai:sidebar-collapsed';

export default function Sidebar() {
    const pathname = usePathname();
    const [collapsed, setCollapsed] = useState(false);

    useEffect(() => {
        try {
            setCollapsed(window.localStorage.getItem(STORAGE_KEY) === '1');
        } catch {
            /* sin localStorage: expandido */
        }
    }, []);

    const toggle = () => {
        setCollapsed((prev) => {
            try {
                window.localStorage.setItem(STORAGE_KEY, prev ? '0' : '1');
            } catch {
                /* noop */
            }
            return !prev;
        });
    };

    const isActive = (path: string) => {
        if (path === '/') return pathname === '/';
        return pathname.startsWith(path);
    };

    return (
        <aside
            className={`hidden md:flex sticky top-16 h-[calc(100vh-4rem)] shrink-0 flex-col border-r border-gray-700/50 bg-gray-900/60 transition-all duration-200 ${
                collapsed ? 'w-16' : 'w-60'
            }`}
        >
            <button
                onClick={toggle}
                title={collapsed ? 'Expandir menú' : 'Plegar menú'}
                aria-label={collapsed ? 'Expandir menú' : 'Plegar menú'}
                className="m-2 flex h-9 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-800 hover:text-teal-300"
            >
                {collapsed ? <ChevronsRight className="h-5 w-5" /> : <ChevronsLeft className="h-5 w-5" />}
            </button>
            <nav className="flex-1 overflow-y-auto px-2 pb-4">
                <ul className="flex flex-col gap-1">
                    {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
                        <li key={href}>
                            <Link
                                href={href}
                                prefetch
                                title={collapsed ? label : undefined}
                                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors hover:bg-gray-800 hover:text-teal-300 ${
                                    isActive(href)
                                        ? 'bg-gray-800 text-gray-100 border-l-2 border-teal-400'
                                        : 'text-gray-400 border-l-2 border-transparent'
                                } ${collapsed ? 'justify-center' : ''}`}
                            >
                                {Icon && <Icon className="h-4 w-4 shrink-0" />}
                                {!collapsed && <span className="truncate">{label}</span>}
                            </Link>
                        </li>
                    ))}
                </ul>
            </nav>
        </aside>
    );
}
