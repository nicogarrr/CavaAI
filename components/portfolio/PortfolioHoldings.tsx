'use client';

import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import Link from 'next/link';
import type { PortfolioHolding } from '@/lib/actions/portfolio.actions';
import { deleteHolding, refreshPortfolioHoldings } from '@/lib/actions/portfolio.actions';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Trash2, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';

type Props = {
  holdings: PortfolioHolding[];
  userId: string;
};

export default function PortfolioHoldings({ holdings, userId }: Props) {
  const router = useRouter();
  const [currentHoldings, setCurrentHoldings] = useState<PortfolioHolding[]>(holdings);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // Sync props if they change (e.g. from server revalidation)
  useEffect(() => {
    setCurrentHoldings(holdings);
  }, [holdings]);

  const handleDelete = async (symbol: string) => {
    if (!confirm(`¿Estás seguro de eliminar toda la posición en ${symbol}? Esto borrará todas las transacciones asociadas.`)) return;

    setDeleting(symbol);
    const result = await deleteHolding(userId, symbol);

    if (result.success) {
      router.refresh();
    } else {
      alert('Error al eliminar la posición');
    }
    setDeleting(null);
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const updated = await refreshPortfolioHoldings(currentHoldings);
      setCurrentHoldings(updated);
    } catch (error) {
      console.error('Error refreshing prices:', error);
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <Card className="bg-gray-800/50 border-gray-700">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-gray-100 flex items-center gap-2">
          Posiciones Actuales
        </CardTitle>
        <Button
          variant="outline"
          size="sm"
          onClick={handleRefresh}
          disabled={refreshing || currentHoldings.length === 0}
          className="h-8 border-gray-600 text-gray-300 hover:bg-gray-700 hover:text-white"
        >
          <RefreshCw className={cn("h-4 w-4 mr-2", refreshing && "animate-spin")} />
          Actualizar Precios
        </Button>
      </CardHeader>
      <CardContent>
        {currentHoldings.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-gray-400">No tienes posiciones abiertas</p>
            <p className="text-sm text-gray-500 mt-2">Agrega tu primera transacción para comenzar</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent border-gray-700">
                  <TableHead className="text-gray-400">Símbolo</TableHead>
                  <TableHead className="text-right text-gray-400">Cantidad</TableHead>
                  <TableHead className="text-right text-gray-400">Promedio</TableHead>
                  <TableHead className="text-right text-gray-400">Actual</TableHead>
                  <TableHead className="text-right text-gray-400">Valor</TableHead>
                  <TableHead className="text-right text-gray-400">G/P</TableHead>
                  <TableHead className="text-center text-gray-400">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {currentHoldings.map((holding) => {
                  const isPositive = holding.gain >= 0;
                  return (
                    <TableRow key={holding.symbol} className="border-gray-700 hover:bg-gray-800/50">
                      <TableCell>
                        <Link
                          href={`/stocks/${holding.symbol}`}
                          className="font-mono font-bold text-teal-400 hover:text-teal-300 transition-colors"
                        >
                          {holding.symbol}
                        </Link>
                      </TableCell>
                      <TableCell className="text-right text-gray-300">
                        {holding.quantity.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right text-gray-300">
                        ${holding.avgPrice.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right text-gray-300 font-medium">
                        ${holding.currentPrice.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right font-semibold text-gray-100">
                        ${holding.value.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex flex-col items-end gap-1">
                          <span className={`font-semibold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                            {isPositive ? '+' : ''}${holding.gain.toFixed(2)}
                          </span>
                          <Badge
                            variant={isPositive ? 'default' : 'destructive'}
                            className={`${isPositive ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30' : 'bg-red-500/20 text-red-400 hover:bg-red-500/30'}`}
                          >
                            {isPositive ? '+' : ''}{holding.gainPercent.toFixed(2)}%
                          </Badge>
                        </div>
                      </TableCell>
                      <TableCell className="text-center">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleDelete(holding.symbol)}
                          disabled={deleting === holding.symbol}
                          className="text-red-400 hover:text-red-300 hover:bg-red-950/20"
                          title="Eliminar posición completa"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
