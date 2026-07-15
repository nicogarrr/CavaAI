'use client';

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { Badge } from '@/components/ui/badge';
import type { CompanyMarketSnapshot } from '@/lib/actions/market-workspace.actions';

function money(value: number | null) {
    return value == null
        ? 'N/A'
        : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
}

export function CompanyMarketPanel({ snapshot }: { snapshot: CompanyMarketSnapshot }) {
    const positive = (snapshot.quote.change ?? 0) >= 0;
    return (
        <div className="space-y-6">
            <section className="rounded-xl border border-gray-800 bg-[#111111] p-5">
                <div className="flex flex-wrap items-start gap-4">
                    <div>
                        <div className="flex items-center gap-2">
                            <h2 className="text-2xl font-semibold text-gray-100">{snapshot.name}</h2>
                            <Badge variant="outline">{snapshot.ticker}</Badge>
                        </div>
                        <p className="mt-1 text-sm text-gray-500">
                            {[snapshot.exchange, snapshot.currency].filter(Boolean).join(' · ') || 'Market metadata unavailable'}
                        </p>
                    </div>
                    <div className="ml-auto text-right">
                        <div className="text-3xl font-bold text-gray-100">{money(snapshot.quote.price)}</div>
                        <div className={positive ? 'text-teal-300' : 'text-red-300'}>
                            {snapshot.quote.change == null ? 'N/A' : `${positive ? '+' : ''}${snapshot.quote.change.toFixed(2)}`}
                            {' · '}
                            {snapshot.quote.changePercent == null ? 'N/A' : `${positive ? '+' : ''}${snapshot.quote.changePercent.toFixed(2)}%`}
                        </div>
                    </div>
                </div>
                <div className="mt-5 grid gap-3 sm:grid-cols-4">
                    {[
                        ['Open', snapshot.quote.open],
                        ['High', snapshot.quote.high],
                        ['Low', snapshot.quote.low],
                        ['Previous close', snapshot.quote.previousClose],
                    ].map(([label, value]) => (
                        <div key={String(label)} className="rounded-lg border border-gray-800 p-3">
                            <div className="text-xs uppercase text-gray-500">{label}</div>
                            <div className="mt-1 font-semibold text-gray-200">{money(value as number | null)}</div>
                        </div>
                    ))}
                </div>
            </section>

            <section className="rounded-xl border border-gray-800 bg-[#111111] p-5">
                <div className="mb-4 flex items-center justify-between">
                    <h3 className="font-semibold text-gray-100">Price history · 1 year</h3>
                    <Badge variant="outline">{snapshot.status}</Badge>
                </div>
                {snapshot.history.length ? (
                    <div className="h-[420px] w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={snapshot.history}>
                                <defs>
                                    <linearGradient id="marketPrice" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#2dd4bf" stopOpacity={0.35} />
                                        <stop offset="95%" stopColor="#2dd4bf" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid stroke="#1f2937" vertical={false} />
                                <XAxis dataKey="date" minTickGap={48} stroke="#6b7280" />
                                <YAxis domain={['auto', 'auto']} stroke="#6b7280" />
                                <Tooltip
                                    contentStyle={{ background: '#111827', border: '1px solid #374151' }}
                                    formatter={(value: number) => [money(value), 'Close']}
                                />
                                <Area type="monotone" dataKey="close" stroke="#2dd4bf" fill="url(#marketPrice)" strokeWidth={2} />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                ) : (
                    <div className="rounded-lg border border-amber-900/60 bg-amber-950/20 p-6 text-sm text-amber-200">
                        Price history is unavailable. The workspace keeps this state explicit and does not fabricate a chart.
                    </div>
                )}
            </section>
        </div>
    );
}
