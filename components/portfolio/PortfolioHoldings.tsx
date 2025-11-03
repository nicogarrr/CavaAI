'use client';

import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { TrendingUp, TrendingDown } from 'lucide-react';
import Link from 'next/link';
import type { PortfolioHolding } from '@/lib/actions/portfolio.actions';

type Props = {
  holdings: PortfolioHolding[];
};

export default function PortfolioHoldings({ holdings }: Props) {
  return (
    <Card className="bg-gray-800/50 border-gray-700">
      <CardHeader>
        <CardTitle className="text-gray-100">Posiciones Actuales</CardTitle>
      </CardHeader>
      <CardContent>
        {holdings.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-gray-400">No tienes posiciones abiertas</p>
            <p className="text-sm text-gray-500 mt-2">Agrega tu primera transacción para comenzar</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Símbolo</TableHead>
                  <TableHead className="text-right">Cantidad</TableHead>
                  <TableHead className="text-right">Precio Promedio</TableHead>
                  <TableHead className="text-right">Precio Actual</TableHead>
                  <TableHead className="text-right">Valor</TableHead>
                  <TableHead className="text-right">G/P</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {holdings.map((holding) => {
                  const isPositive = holding.gain >= 0;
                  return (
                    <TableRow key={holding.symbol}>
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
                      <TableCell className="text-right text-gray-300">
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
                            className="text-xs"
                          >
                            {isPositive ? '+' : ''}{holding.gainPercent.toFixed(2)}%
                          </Badge>
                        </div>
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
