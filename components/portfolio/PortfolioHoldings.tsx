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
import { toast } from 'sonner';
import { getErrorMessage } from '@/lib/types/errors';

type Props = {
  holdings: PortfolioHolding[];
  userId: string;
};

export default function PortfolioHoldings({ holdings, userId }: Props) {
  const router = useRouter();
  const [currentHoldings, setCurrentHoldings] = useState<PortfolioHolding[]>(holdings);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const format = (value: number, currency: string) => new Intl.NumberFormat('en-US', {
    style: 'currency', currency, maximumFractionDigits: 2,
  }).format(value);

  // Sync props if they change (e.g. from server revalidation)
  useEffect(() => {
    setCurrentHoldings(holdings);
  }, [holdings]);

  const handleDelete = async (symbol: string) => {
    if (!confirm(`¿Estás seguro de eliminar toda la posición en ${symbol}? Esto borrará todas las transacciones asociadas.`)) return;

    setDeleting(symbol);
    try {
      await deleteHolding(userId, symbol);
      toast.success(`Posición ${symbol} eliminada`);
      router.refresh();
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setDeleting(null);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const updated = await refreshPortfolioHoldings(currentHoldings);
      setCurrentHoldings(updated);
      toast.success('Precios actualizados');
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <Card className="bg-gray-800/50 border-gray-700">
      <CardHeader className="flex flex-col gap-3 pb-2 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="text-gray-100 flex items-center gap-2">
          Posiciones Actuales
        </CardTitle>
        <Button
          variant="outline"
          size="sm"
          onClick={handleRefresh}
          disabled={refreshing || currentHoldings.length === 0}
          className="h-11 border-gray-600 text-gray-300 hover:bg-gray-700 hover:text-white sm:h-8"
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
          <>
            {/* Móvil: cards sin scroll horizontal */}
            <div className="space-y-3 md:hidden">
              {currentHoldings.map((holding) => {
                const isPositive = holding.gain >= 0;
                return (
                  <div key={holding.symbol} className="rounded-xl border border-gray-700 p-4">
                    <div className="flex items-center justify-between gap-2">
                      <Link
                        href={`/research/${holding.symbol}`}
                        className="font-mono text-lg font-bold text-teal-400 hover:text-teal-300"
                      >
                        {holding.symbol}
                      </Link>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(holding.symbol)}
                        disabled={deleting === holding.symbol}
                        className="min-h-[44px] min-w-[44px] text-red-400 hover:text-red-300 hover:bg-red-950/20"
                        title="Eliminar posición completa"
                        aria-label={`Eliminar posición en ${holding.symbol}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                    <dl className="mt-3 space-y-1.5 text-sm">
                      <div className="flex justify-between gap-2"><dt className="text-gray-500">Cantidad</dt><dd className="text-gray-200">{holding.quantity.toFixed(2)}</dd></div>
                      <div className="flex justify-between gap-2"><dt className="text-gray-500">Promedio</dt><dd className="text-gray-200">{format(holding.avgPrice, holding.nativeCurrency)}</dd></div>
                      <div className="flex justify-between gap-2"><dt className="text-gray-500">Actual</dt><dd className="font-medium text-gray-200">{format(holding.currentPrice, holding.nativeCurrency)}</dd></div>
                      <div className="flex justify-between gap-2"><dt className="text-gray-500">Valor</dt><dd className="font-semibold text-gray-100">{holding.fxMissing ? 'FX missing' : format(holding.value, holding.baseCurrency)}</dd></div>
                      <div className="flex items-center justify-between gap-2">
                        <dt className="text-gray-500">G/P</dt>
                        <dd className="flex items-center gap-2">
                          <span className={`font-semibold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                            {holding.fxMissing ? 'N/A' : `${isPositive ? '+' : ''}${format(holding.gain, holding.baseCurrency)}`}
                          </span>
                          <Badge
                            variant={isPositive ? 'default' : 'destructive'}
                            className={`${isPositive ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30' : 'bg-red-500/20 text-red-400 hover:bg-red-500/30'}`}
                          >
                            {isPositive ? '+' : ''}{holding.gainPercent.toFixed(2)}%
                          </Badge>
                        </dd>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <dt className="text-gray-500">Fiscal</dt>
                        <dd>
                          {holding.fiscalBucket ? (
                            <Badge
                              variant="outline"
                              className={
                                holding.fiscalBucket === 'largo_plazo'
                                  ? 'border-blue-700 text-blue-300'
                                  : 'border-amber-700 text-amber-300'
                              }
                            >
                              {holding.fiscalBucket === 'largo_plazo' ? 'Largo plazo' : 'Corto plazo'}
                              {holding.holdingDays !== null ? ` · ${holding.holdingDays}d` : ''}
                            </Badge>
                          ) : (
                            <span className="text-xs text-gray-600">N/D</span>
                          )}
                        </dd>
                      </div>
                    </dl>
                  </div>
                );
              })}
            </div>
            {/* Escritorio: tabla completa */}
            <div className="hidden overflow-x-auto md:block">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent border-gray-700">
                  <TableHead className="text-gray-400">Símbolo</TableHead>
                  <TableHead className="text-right text-gray-400">Cantidad</TableHead>
                  <TableHead className="text-right text-gray-400">Promedio</TableHead>
                  <TableHead className="text-right text-gray-400">Actual</TableHead>
                  <TableHead className="text-right text-gray-400">Valor</TableHead>
                  <TableHead className="text-right text-gray-400">G/P</TableHead>
                  <TableHead className="text-center text-gray-400">Fiscal</TableHead>
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
                          href={`/research/${holding.symbol}`}
                          className="font-mono font-bold text-teal-400 hover:text-teal-300 transition-colors"
                        >
                          {holding.symbol}
                        </Link>
                      </TableCell>
                      <TableCell className="text-right text-gray-300">
                        {holding.quantity.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right text-gray-300">
                        {format(holding.avgPrice, holding.nativeCurrency)}
                      </TableCell>
                      <TableCell className="text-right text-gray-300 font-medium">
                        {format(holding.currentPrice, holding.nativeCurrency)}
                      </TableCell>
                      <TableCell className="text-right font-semibold text-gray-100">
                        {holding.fxMissing ? <Badge variant="outline">FX missing</Badge> : format(holding.value, holding.baseCurrency)}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex flex-col items-end gap-1">
                          <span className={`font-semibold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                            {holding.fxMissing ? 'N/A' : `${isPositive ? '+' : ''}${format(holding.gain, holding.baseCurrency)}`}
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
                        {holding.fiscalBucket ? (
                          <div className="flex flex-col items-center gap-1">
                            <Badge
                              variant="outline"
                              className={
                                holding.fiscalBucket === 'largo_plazo'
                                  ? 'border-blue-700 text-blue-300'
                                  : 'border-amber-700 text-amber-300'
                              }
                              title={
                                holding.firstBuyDate
                                  ? `En cartera desde ${holding.firstBuyDate}`
                                  : undefined
                              }
                            >
                              {holding.fiscalBucket === 'largo_plazo' ? 'Largo plazo' : 'Corto plazo'}
                            </Badge>
                            {holding.holdingDays !== null && (
                              <span className="text-xs text-gray-500">{holding.holdingDays}d</span>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-gray-600" title="Sin historial de compra registrado">
                            N/D
                          </span>
                        )}
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
          </>
        )}
      </CardContent>
    </Card>
  );
}
