'use client';

import { Button } from '@/components/ui/button';
import { Trash2, ExternalLink } from 'lucide-react';
import { removePosition } from '@/lib/actions/portfolio.actions';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

type PositionsTableProps = {
    positions: PortfolioPositionWithData[];
    portfolioId: string;
};

export default function PositionsTable({ positions, portfolioId }: PositionsTableProps) {
    const router = useRouter();

    const formatCurrency = (value: number) => {
        return new Intl.NumberFormat('es-ES', {
            style: 'currency',
            currency: 'USD',
        }).format(value);
    };

    const handleRemove = async (index: number, symbol: string) => {
        if (!confirm(`¿Eliminar ${symbol} de la cartera?`)) {
            return;
        }

        try {
            await removePosition(portfolioId, index);
            toast.success('Posición eliminada');
            router.refresh();
        } catch (error) {
            console.error('Error al eliminar posición:', error);
            toast.error('Error al eliminar la posición');
        }
    };

    if (positions.length === 0) {
        return (
            <div className="border rounded-lg p-12 text-center">
                <p className="text-muted-foreground">No hay posiciones en esta cartera</p>
            </div>
        );
    }

    return (
        <div className="border rounded-lg overflow-hidden">
            <div className="overflow-x-auto">
                <table className="w-full">
                    <thead className="bg-muted">
                        <tr>
                            <th className="text-left p-4 font-semibold">Símbolo</th>
                            <th className="text-left p-4 font-semibold">Compañía</th>
                            <th className="text-right p-4 font-semibold">Acciones</th>
                            <th className="text-right p-4 font-semibold">Precio Compra</th>
                            <th className="text-right p-4 font-semibold">Precio Actual</th>
                            <th className="text-right p-4 font-semibold">Invertido</th>
                            <th className="text-right p-4 font-semibold">Valor Actual</th>
                            <th className="text-right p-4 font-semibold">G/P</th>
                            <th className="text-center p-4 font-semibold">Acciones</th>
                        </tr>
                    </thead>
                    <tbody>
                        {positions.map((position, index) => {
                            const isProfit = position.profitLoss >= 0;
                            return (
                                <tr key={position.symbol} className="border-t hover:bg-muted/50">
                                    <td className="p-4 font-medium">{position.symbol}</td>
                                    <td className="p-4">{position.company}</td>
                                    <td className="p-4 text-right">{position.shares}</td>
                                    <td className="p-4 text-right">
                                        {formatCurrency(position.avgPurchasePrice)}
                                    </td>
                                    <td className="p-4 text-right">
                                        {formatCurrency(position.currentPrice)}
                                    </td>
                                    <td className="p-4 text-right">
                                        {formatCurrency(position.invested)}
                                    </td>
                                    <td className="p-4 text-right">
                                        {formatCurrency(position.currentValue)}
                                    </td>
                                    <td className={`p-4 text-right font-medium ${isProfit ? 'text-green-500' : 'text-red-500'}`}>
                                        {formatCurrency(position.profitLoss)}
                                        <br />
                                        <span className="text-sm">
                                            ({isProfit ? '+' : ''}{position.profitLossPercent.toFixed(2)}%)
                                        </span>
                                    </td>
                                    <td className="p-4 text-center">
                                        <div className="flex items-center justify-center gap-2">
                                            <Link href={`/stocks/${position.symbol}`}>
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    title="Ver ficha detallada"
                                                >
                                                    <ExternalLink className="h-4 w-4" />
                                                </Button>
                                            </Link>
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                onClick={() => handleRemove(index, position.symbol)}
                                                title="Eliminar posición"
                                            >
                                                <Trash2 className="h-4 w-4 text-destructive" />
                                            </Button>
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

