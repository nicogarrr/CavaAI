'use client';

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

import { Dividend, getDividends } from "@/lib/actions/fmp.actions";
import { DollarSign, Calendar } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

interface StockDividendsProps {
    symbol: string;
}

export default function StockDividends({ symbol }: StockDividendsProps) {
    const [dividends, setDividends] = useState<Dividend[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            try {
                const data = await getDividends(symbol);
                setDividends(data);
            } catch (error) {
                console.error("Failed to fetch dividends", error);
            } finally {
                setLoading(false);
            }
        };

        if (symbol) {
            fetchData();
        }
    }, [symbol]);

    if (loading) {
        return <Skeleton className="h-[400px] w-full rounded-lg bg-gray-800/50" />;
    }

    if (!dividends || dividends.length === 0) {
        return (
            <Card className="bg-gray-900 border-gray-800">
                <CardHeader>
                    <CardTitle className="text-gray-100 flex items-center gap-2">
                        <DollarSign className="h-5 w-5 text-green-500" />
                        Historial de Dividendos
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-gray-400 py-10 text-center">No hay información de dividendos disponible para {symbol}.</p>
                </CardContent>
            </Card>
        );
    }

    // Sort by date desc
    const sortedDividends = [...dividends].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

    // Calculate annual yield estimate based on last 4 quarters (roughly)
    const recent = sortedDividends.slice(0, 4);
    const ttmTotal = recent.reduce((sum, d) => sum + d.dividend, 0);

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card className="bg-gray-900 border-gray-800">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-gray-400">Último Dividendo</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-gray-100">${sortedDividends[0]?.dividend.toFixed(4)}</div>
                        <p className="text-xs text-gray-500 mt-1">
                            {new Date(sortedDividends[0]?.date).toLocaleDateString()}
                        </p>
                    </CardContent>
                </Card>
                <Card className="bg-gray-900 border-gray-800">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-gray-400">Frecuencia</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-gray-100">Trimestral</div>
                        <p className="text-xs text-gray-500 mt-1">Estimada</p>
                    </CardContent>
                </Card>
                <Card className="bg-gray-900 border-gray-800">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-gray-400">Dividendo TTM</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-green-400">${ttmTotal.toFixed(2)}</div>
                        <p className="text-xs text-gray-500 mt-1">Últimos 12 meses (aprox)</p>
                    </CardContent>
                </Card>
            </div>

            <Card className="bg-gray-900 border-gray-800">
                <CardHeader>
                    <CardTitle className="text-gray-100 flex items-center gap-2">
                        <Calendar className="h-5 w-5 text-blue-500" />
                        Historial de Pagos
                    </CardTitle>
                    <CardDescription className="text-gray-400">
                        Histórico de dividendos declarados y pagados
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <Table>
                        <TableHeader>
                            <TableRow className="border-gray-800 hover:bg-transparent">
                                <TableHead className="text-gray-400">Fecha Ex</TableHead>
                                <TableHead className="text-gray-400">Pago</TableHead>
                                <TableHead className="text-gray-400">Declaración</TableHead>
                                <TableHead className="text-right text-gray-400">Monto</TableHead>
                                <TableHead className="text-right text-gray-400">Ajustado</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {sortedDividends.map((div, i) => (
                                <TableRow key={i} className="border-gray-800 hover:bg-gray-800/50">
                                    <TableCell className="text-gray-200 font-medium">
                                        {new Date(div.date).toLocaleDateString()}
                                    </TableCell>
                                    <TableCell className="text-gray-400">
                                        {div.paymentDate ? new Date(div.paymentDate).toLocaleDateString() : '-'}
                                    </TableCell>
                                    <TableCell className="text-gray-400">
                                        {div.declarationDate ? new Date(div.declarationDate).toLocaleDateString() : '-'}
                                    </TableCell>
                                    <TableCell className="text-right text-green-400 font-bold">
                                        ${div.dividend.toFixed(4)}
                                    </TableCell>
                                    <TableCell className="text-right text-gray-400">
                                        ${div.adjDividend.toFixed(4)}
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </CardContent>
            </Card>
        </div>
    );
}
