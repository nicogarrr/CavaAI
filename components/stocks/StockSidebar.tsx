'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import {
    LayoutDashboard,
    TrendingUp,
    Shield,
    BarChart3,
    Brain,
    Newspaper,
    ChevronLeft,
    ChevronRight,
} from 'lucide-react';

export type StockTab =
    | 'resumen'
    | 'valoracion'
    | 'calidad'
    | 'fundamentales'
    | 'analisis'
    | 'noticias';

interface NavItem {
    id: StockTab;
    label: string;
    icon: React.ReactNode;
    description?: string;
}

const navItems: NavItem[] = [
    {
        id: 'resumen',
        label: 'Resumen',
        icon: <LayoutDashboard size={20} />,
        description: 'Gráfico y datos básicos'
    },
    {
        id: 'valoracion',
        label: 'Valoración',
        icon: <TrendingUp size={20} />,
        description: 'DCF, Ratios, EV'
    },
    {
        id: 'calidad',
        label: 'Calidad',
        icon: <Shield size={20} />,
        description: 'Health Score, Scores'
    },
    {
        id: 'fundamentales',
        label: 'Fundamentales',
        icon: <BarChart3 size={20} />,
        description: 'Revenue, Margins, Debt'
    },
    {
        id: 'analisis',
        label: 'Análisis',
        icon: <Brain size={20} />,
        description: 'AI Checklist, Patterns'
    },
    {
        id: 'noticias',
        label: 'Noticias',
        icon: <Newspaper size={20} />,
        description: 'Últimas noticias'
    },
];

interface StockSidebarProps {
    activeTab: StockTab;
    onTabChange: (tab: StockTab) => void;
    symbol: string;
    className?: string;
}

export default function StockSidebar({
    activeTab,
    onTabChange,
    symbol,
    className
}: StockSidebarProps) {
    const [collapsed, setCollapsed] = useState(false);

    return (
        <aside
            className={cn(
                "flex flex-col h-full bg-gray-900/95 border-r border-gray-700/50",
                "transition-all duration-300 ease-in-out",
                collapsed ? "w-16" : "w-56",
                className
            )}
        >
            {/* Symbol Header */}
            <div className={cn(
                "px-4 py-4 border-b border-gray-700/50",
                collapsed && "px-2"
            )}>
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-bold text-sm shrink-0">
                        {symbol.slice(0, 2)}
                    </div>
                    {!collapsed && (
                        <div className="overflow-hidden">
                            <p className="font-semibold text-gray-100 truncate">{symbol}</p>
                            <p className="text-xs text-gray-400">Stock Analysis</p>
                        </div>
                    )}
                </div>
            </div>

            {/* Navigation */}
            <nav className="flex-1 py-4 space-y-1 px-2">
                {navItems.map((item) => (
                    <button
                        key={item.id}
                        onClick={() => onTabChange(item.id)}
                        className={cn(
                            "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg",
                            "text-left transition-all duration-200",
                            "hover:bg-gray-800/60",
                            activeTab === item.id
                                ? "bg-blue-600/20 text-blue-400 border-l-2 border-blue-500"
                                : "text-gray-400 hover:text-gray-200",
                            collapsed && "justify-center px-2"
                        )}
                        title={collapsed ? item.label : undefined}
                    >
                        <span className={cn(
                            "shrink-0",
                            activeTab === item.id ? "text-blue-400" : ""
                        )}>
                            {item.icon}
                        </span>
                        {!collapsed && (
                            <div className="overflow-hidden">
                                <p className="font-medium text-sm">{item.label}</p>
                                {item.description && (
                                    <p className="text-xs text-gray-500 truncate">
                                        {item.description}
                                    </p>
                                )}
                            </div>
                        )}
                    </button>
                ))}
            </nav>

            {/* Collapse Button */}
            <div className="p-2 border-t border-gray-700/50">
                <button
                    onClick={() => setCollapsed(!collapsed)}
                    className={cn(
                        "w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg",
                        "text-gray-400 hover:text-gray-200 hover:bg-gray-800/60",
                        "transition-all duration-200"
                    )}
                >
                    {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
                    {!collapsed && <span className="text-sm">Colapsar</span>}
                </button>
            </div>
        </aside>
    );
}
