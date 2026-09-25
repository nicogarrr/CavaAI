'use client';

import { formatMoney, formatPercent } from '@/lib/format';
import { TrendingUp, TrendingDown, DollarSign, PiggyBank } from 'lucide-react';
import type { PortfolioSummary as PortfolioSummaryType } from '@/lib/actions/portfolio.actions';

type Props = {
  summary: PortfolioSummaryType;
};

export default function PortfolioSummary({ summary }: Props) {
  // Cartera vacia: un "+0,00%" en verde sugiere ganancia donde no hay datos (F31)
  const isEmpty = summary.holdings.length === 0;
  const isPositive = summary.totalGain >= 0;
  const format = (value: number) => formatMoney(value, summary.baseCurrency, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  return (
    <div className="space-y-3">
      {summary.status === 'incomplete_fx' ? (
        <div className="rounded-lg border border-amber-800/70 bg-amber-950/30 p-3 text-sm text-amber-200">
          Portfolio totals exclude {summary.missingFx.length} balance or position without a valid FX rate.
        </div>
      ) : null}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-4">
      <div className="bg-[#111111] border border-gray-800 rounded-xl p-4 sm:p-5 relative overflow-hidden group hover:border-teal-500/30 transition-colors">
        <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
          <DollarSign className="h-12 w-12 text-teal-400" />
        </div>
        <p className="text-gray-400 text-xs uppercase tracking-wider font-semibold mb-1">Valor Total</p>
        <p className="text-xl sm:text-2xl font-bold text-gray-100 tracking-tight">
          {format(summary.totalValue)}
        </p>
      </div>

      <div className="bg-[#111111] border border-gray-800 rounded-xl p-4 sm:p-5 relative overflow-hidden group hover:border-blue-500/30 transition-colors">
        <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
          <PiggyBank className="h-12 w-12 text-blue-400" />
        </div>
        <p className="text-gray-400 text-xs uppercase tracking-wider font-semibold mb-1">Costo Total</p>
        <p className="text-xl sm:text-2xl font-bold text-gray-100 tracking-tight">
          {format(summary.totalCost)}
        </p>
      </div>

      <div className="bg-[#111111] border border-gray-800 rounded-xl p-4 sm:p-5 relative overflow-hidden group hover:border-purple-500/30 transition-colors">
        <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
          {!isEmpty ? (
            isPositive ? (
              <TrendingUp className="h-12 w-12 text-green-500" />
            ) : (
              <TrendingDown className="h-12 w-12 text-red-500" />
            )
          ) : null}
        </div>
        <p className="text-gray-400 text-[11px] sm:text-xs uppercase tracking-normal sm:tracking-wider font-semibold mb-1">Ganancia/Pérdida</p>
        <p className={`text-xl sm:text-2xl font-bold tracking-tight ${isEmpty ? 'text-gray-500' : isPositive ? 'text-green-400' : 'text-red-400'}`}>
          {isEmpty ? 's/d' : `${isPositive ? '+' : ''}${format(summary.totalGain)}`}
        </p>
      </div>

      <div className="bg-[#111111] border border-gray-800 rounded-xl p-4 sm:p-5 relative overflow-hidden group hover:border-orange-500/30 transition-colors">
        <p className="text-gray-400 text-xs uppercase tracking-wider font-semibold mb-1">Rendimiento</p>
        <div className="flex items-baseline gap-2">
          <p className={`text-xl sm:text-2xl font-bold tracking-tight ${isEmpty ? 'text-gray-500' : isPositive ? 'text-green-400' : 'text-red-400'}`}>
            {isEmpty ? 's/d' : formatPercent(summary.totalGainPercent, { fromRatio: false, digits: 2, signDisplay: 'always' })}
          </p>
        </div>
        {/* Barra de progreso visual */}
        {!isEmpty ? (
          <div className="w-full bg-gray-800 h-1.5 rounded-full mt-3 overflow-hidden">
            <div
              className={`h-full rounded-full ${isPositive ? 'bg-green-500' : 'bg-red-500'}`}
              style={{ width: `${Math.min(Math.abs(summary.totalGainPercent), 100)}%` }}
            />
          </div>
        ) : null}
      </div>
      </div>
    </div>
  );
}
