'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Loader2, TrendingUp, Award, RefreshCw } from 'lucide-react';
import { getFundRanking, getFundCategories } from '@/lib/actions/funds.actions';
import { Button } from '@/components/ui/button';

// Major categories for Spanish investors - matching Finect scraping
const DEFAULT_CATEGORIES = [
    { id: 'default', name: 'Todos los Fondos' },
    { id: 'world', name: 'RV Global' },
    { id: 'sp500', name: 'RV USA / S&P 500' },
    { id: 'europa', name: 'RV Europa' },
    { id: 'emergentes', name: 'RV Emergentes' },
    { id: 'asia', name: 'RV Asia' },
    { id: 'tech', name: 'RV Sector Tecnología' },
    { id: 'oro', name: 'RV Sector Oro y Metales' },
    { id: 'salud', name: 'RV Sector Salud' },
    { id: 'energia', name: 'RV Sector Energía' },
    { id: 'espana', name: 'RV España' },
];

interface Fund {
    rank: number;
    name: string;
    isin: string;
    category: string;
    tipo: string;
    return1Y: number;
    return3Y: number;
    return5Y: number;
    volatility: number;
    ter: number;
}

interface Category {
    id: string;
    name: string;
    url?: string;
}

export function FundRankingTable() {
    const [selectedCategory, setSelectedCategory] = useState("default");
    const [selectedIndexed, setSelectedIndexed] = useState("all"); // 'all', 'true', 'false'
    const [loading, setLoading] = useState(false);
    const [loadingCategories, setLoadingCategories] = useState(true);
    const [funds, setFunds] = useState<Fund[]>([]);
    const [categories, setCategories] = useState<Category[]>(DEFAULT_CATEGORIES);

    // Load categories on mount - DISABLED: Using DEFAULT_CATEGORIES with correct IDs
    // The backend /funds/categories returns numeric IDs that don't match CATEGORY_FILTER_MAP
    useEffect(() => {
        // Categories are already set from DEFAULT_CATEGORIES
        setLoadingCategories(false);
    }, []);

    // Load funds when category or indexed filter changes
    useEffect(() => {
        fetchFunds();
    }, [selectedCategory, selectedIndexed]);

    async function fetchFunds() {
        setLoading(true);
        const res = await getFundRanking(selectedCategory, 10, selectedIndexed);
        if (res.success) {
            setFunds(res.data || []);
        } else {
            setFunds([]);
        }
        setLoading(false);
    }

    const currentLabel = categories.find(c => c.id === selectedCategory)?.name || "Fondos";

    return (
        <Card className="bg-slate-950 border-slate-800 shadow-2xl">
            <CardHeader className="flex flex-col md:flex-row items-start md:items-center justify-between pb-4 border-b border-slate-800">
                <div className="mb-4 md:mb-0">
                    <CardTitle className="text-xl font-bold text-green-400 flex items-center gap-2">
                        <Award className="h-5 w-5" />
                        Ranking de Fondos: <span className="text-white">{currentLabel}</span>
                    </CardTitle>
                    <p className="text-sm text-slate-400 mt-1">Top 10 fondos por rentabilidad 12M (Fuente: Finect)</p>
                </div>

                <div className="flex items-center gap-2">
                    <Select value={selectedCategory} onValueChange={setSelectedCategory}>
                        <SelectTrigger className="w-[200px] bg-slate-900 border-slate-700 text-slate-200">
                            <SelectValue placeholder="Selecciona Categoría" />
                        </SelectTrigger>
                        <SelectContent className="bg-slate-900 border-slate-700 text-slate-200 max-h-[300px]">
                            {categories.map(cat => (
                                <SelectItem key={cat.id} value={cat.id}>{cat.name}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>

                    <Select value={selectedIndexed} onValueChange={setSelectedIndexed}>
                        <SelectTrigger className="w-[150px] bg-slate-900 border-slate-700 text-slate-200">
                            <SelectValue placeholder="Gestión" />
                        </SelectTrigger>
                        <SelectContent className="bg-slate-900 border-slate-700 text-slate-200">
                            <SelectItem value="all">Todas</SelectItem>
                            <SelectItem value="true">Pasiva (Indexados)</SelectItem>
                            <SelectItem value="false">Activa</SelectItem>
                        </SelectContent>
                    </Select>

                    <Button
                        variant="outline"
                        size="icon"
                        onClick={fetchFunds}
                        disabled={loading}
                        className="border-slate-700 hover:bg-slate-800"
                    >
                        <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                    </Button>
                </div>
            </CardHeader>

            <CardContent className="p-0">
                <div className="overflow-x-auto">
                    <Table>
                        <TableHeader className="bg-slate-900 text-green-500 hover:bg-slate-900/50">
                            <TableRow className="border-slate-800 hover:bg-transparent">
                                <TableHead className="text-green-500 font-bold uppercase text-xs w-[50px]">Rank</TableHead>
                                <TableHead className="text-green-500 font-bold uppercase text-xs">Nombre</TableHead>
                                <TableHead className="text-green-500 font-bold uppercase text-xs">ISIN</TableHead>
                                <TableHead className="text-green-500 font-bold uppercase text-xs hidden lg:table-cell">Categoría</TableHead>
                                <TableHead className="text-green-500 font-bold uppercase text-xs text-right">Rent. 12M</TableHead>
                                <TableHead className="text-green-500 font-bold uppercase text-xs text-right hidden md:table-cell">Rent. 5A</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {loading ? (
                                <TableRow>
                                    <TableCell colSpan={6} className="h-32 text-center text-slate-400">
                                        <div className="flex flex-col items-center justify-center gap-2">
                                            <Loader2 className="h-8 w-8 animate-spin text-green-500" />
                                            <p>Cargando fondos desde Finect...</p>
                                        </div>
                                    </TableCell>
                                </TableRow>
                            ) : funds.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={6} className="h-24 text-center text-slate-400">
                                        No se encontraron datos para esta categoría.
                                    </TableCell>
                                </TableRow>
                            ) : (
                                funds.map((fund) => (
                                    <TableRow key={fund.isin} className="border-slate-800 hover:bg-slate-900/50 transition-colors group">
                                        <TableCell className="font-bold text-slate-300 group-hover:text-green-400">
                                            #{fund.rank}
                                        </TableCell>
                                        <TableCell className="font-medium text-slate-100 max-w-[250px] truncate" title={fund.name}>
                                            {fund.name}
                                        </TableCell>
                                        <TableCell className="text-xs text-slate-400 font-mono">
                                            {fund.isin}
                                        </TableCell>
                                        <TableCell className="text-xs text-slate-400 hidden lg:table-cell max-w-[150px] truncate" title={fund.category}>
                                            {fund.category || '-'}
                                        </TableCell>
                                        <TableCell className={`text-right font-bold ${fund.return1Y >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                            {fund.return1Y ? `${fund.return1Y.toFixed(2)}%` : '-'}
                                        </TableCell>
                                        <TableCell className={`text-right hidden md:table-cell ${fund.return5Y >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                            {fund.return5Y ? `${fund.return5Y.toFixed(2)}%` : '-'}
                                        </TableCell>
                                    </TableRow>
                                ))
                            )}
                        </TableBody>
                    </Table>
                </div>
            </CardContent>
        </Card>
    );
}
