'use client';

import { Card, CardContent } from '@/components/ui/card';
import { TrendingUp, TrendingDown, DollarSign, PiggyBank } from 'lucide-react';
import type { PortfolioSummary as PortfolioSummaryType } from '@/lib/actions/portfolio.actions';

type Props = {
  summary: PortfolioSummaryType;
};

export default function PortfolioSummary({ summary }: Props) {
  const isPositive = summary.totalGain >= 0;

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
      <Card className="bg-gray-800/50 border-gray-700">
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-400 mb-1">Valor Total</p>
              <p className="text-2xl font-bold text-gray-100">
                ${summary.totalValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
            </div>
            <DollarSign className="h-8 w-8 text-teal-400" />
          </div>
        </CardContent>
      </Card>

      <Card className="bg-gray-800/50 border-gray-700">
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-400 mb-1">Costo Total</p>
              <p className="text-2xl font-bold text-gray-100">
                ${summary.totalCost.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
            </div>
            <PiggyBank className="h-8 w-8 text-gray-400" />
          </div>
        </CardContent>
      </Card>

      <Card className="bg-gray-800/50 border-gray-700">
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-400 mb-1">Ganancia/Pérdida</p>
              <p className={`text-2xl font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                {isPositive ? '+' : ''}${summary.totalGain.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
            </div>
            {isPositive ? (
              <TrendingUp className="h-8 w-8 text-green-400" />
            ) : (
              <TrendingDown className="h-8 w-8 text-red-400" />
            )}
          </div>
        </CardContent>
      </Card>

      <Card className="bg-gray-800/50 border-gray-700">
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-400 mb-1">Rendimiento</p>
              <p className={`text-2xl font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                {isPositive ? '+' : ''}{summary.totalGainPercent.toFixed(2)}%
              </p>
            </div>
            {isPositive ? (
              <TrendingUp className="h-8 w-8 text-green-400" />
            ) : (
              <TrendingDown className="h-8 w-8 text-red-400" />
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
