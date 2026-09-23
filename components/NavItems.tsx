'use client'


import React from 'react'
import {NAV_SECTIONS} from "@/lib/constants";
import Link from "next/link";
import {usePathname} from "next/navigation";

const NavItems = ({initialStocks}: { initialStocks: StockWithWatchlistStatus[]}) => {
    const pathname = usePathname()
    void initialStocks;

    const isActive = (path: string) => {
        if (path ==='/') return pathname === '/'
        return pathname.startsWith(path);
    }

    return (
        <ul className="flex max-w-full flex-col gap-1 p-2 text-sm font-medium">
            {NAV_SECTIONS.map((section) => (
                <li key={section.title}>
                    <p className="px-1 pb-1 pt-4 text-xs font-semibold uppercase tracking-wide text-gray-600">
                        {section.title}
                    </p>
                    <ul className="flex flex-col gap-1">
                        {section.items.map(({href, label, icon: Icon}) => (
                            <li key={href} className="shrink-0">
                                <Link
                                    href={href}
                                    prefetch
                                    className={`flex min-h-[44px] cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-base transition-colors hover:text-teal-500 ${isActive(href) ? 'bg-gray-800/70 text-gray-100' : 'text-gray-400'}`}
                                >
                                    {Icon && <Icon className="h-4 w-4" />}
                                    {label}
                                </Link>
                            </li>
                        ))}
                    </ul>
                </li>
            ))}
        </ul>
    )
}
export default NavItems