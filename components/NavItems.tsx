'use client'


import React from 'react'
import {NAV_ITEMS} from "@/lib/constants";
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
        <ul className="flex flex-col sm:flex-row p-2 gap-3 sm:gap-4 font-medium text-sm max-w-full sm:overflow-x-auto scrollbar-hide">
            {NAV_ITEMS.map(({href, label, icon: Icon}) => (
                <li key={href} className="shrink-0">
                    <Link 
                        href={href} 
                        prefetch={false}
                        className={`flex items-center gap-1.5 hover:text-teal-500 transition-colors cursor-pointer ${isActive(href) ? 'text-gray-100' : 'text-gray-400'}`}
                    >
                        {Icon && <Icon className="h-4 w-4" />}
                        {label}
                    </Link>
                </li>
            ))}
        </ul>
    )
}
export default NavItems