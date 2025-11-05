'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { getFundCategories, type FundCategory, type FundRecord } from '@/lib/actions/fundsRanking.actions';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';

async function fetchRankings(category: FundCategory): Promise<FundRecord[]> {
  // Llamada al server action vía fetch API (route handler interno)
  const res = await fetch(`/api/funds/rank?category=${category}`, { cache: 'no-store' });
  if (!res.ok) return [] as FundRecord[];
  return await res.json();
}

export default function FundRankings() {
  const [categories, setCategories] = useState<{ id: FundCategory; label: string }[]>([]);
  const [category, setCategory] = useState<FundCategory>('msci_world');
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<FundRecord[]>([]);

  useEffect(() => {
    getFundCategories().then(setCategories);
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchRankings(category)
      .then((d) => { if (active) setData(d); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [category]);

  const columns = useMemo(() => ([
    { key: 'rank', label: '#'},
    { key: 'name', label: 'Fondo/ETF' },
    { key: 'provider', label: 'Gestora' },
    { key: 'expenseRatio', label: 'TER %' },
    { key: 'y1', label: '1Y %' },
    { key: 'y3', label: '3Y %' },
    { key: 'y5', label: '5Y %' },
    { key: 'trackingDifference', label: 'TrackDiff %' },
    { key: 'aumMillions', label: 'AUM (M)' },
    { key: 'replication', label: 'Replica' },
    { key: 'score', label: 'Score' },
  ]), []);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-4">
          <CardTitle>Ranking de Fondos/ETFs por Categoría</CardTitle>
          <div className="w-64">
            <Select value={category} onValueChange={(v) => setCategory(v as FundCategory)}>
              <SelectTrigger aria-label="Seleccionar categoría">
                <SelectValue placeholder="Elige categoría" />
              </SelectTrigger>
              <SelectContent>
                {categories.map((c) => (
                  <SelectItem key={c.id} value={c.id}>{c.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div role="status" aria-live="polite" className="text-sm text-muted-foreground">Cargando ranking…</div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                {columns.map((c) => (
                  <TableHead key={c.key}>{c.label}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((row, idx) => (
                <TableRow key={(row.isin || row.symbol || row.name) + idx}>
                  <TableCell>{idx + 1}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{row.name}</span>
                      {row.distributing != null && (
                        <Badge variant="secondary">{row.distributing ? 'Distribución' : 'Acumulación'}</Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>{row.provider || '-'}</TableCell>
                  <TableCell>{row.expenseRatio != null ? row.expenseRatio.toFixed(2) : '-'}</TableCell>
                  <TableCell>{row.y1 != null ? row.y1.toFixed(2) : '-'}</TableCell>
                  <TableCell>{row.y3 != null ? row.y3.toFixed(2) : '-'}</TableCell>
                  <TableCell>{row.y5 != null ? row.y5.toFixed(2) : '-'}</TableCell>
                  <TableCell>{row.trackingDifference != null ? row.trackingDifference.toFixed(2) : '-'}</TableCell>
                  <TableCell>{row.aumMillions != null ? Math.round(row.aumMillions) : '-'}</TableCell>
                  <TableCell>{row.replication || '-'}</TableCell>
                  <TableCell>{row.score?.toFixed(1) ?? '-'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}


