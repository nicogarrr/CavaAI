'use client';

import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Slider } from '@/components/ui/slider';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { TrendingUp, TrendingDown, ExternalLink, Star } from 'lucide-react';
import Link from 'next/link';
import { screenStocks, ScreenerFilters, ScreenerResult } from '@/lib/actions/screener.actions';

const defaultFilters: ScreenerFilters = {
  marketCapMin: 0,
  marketCapMax: 1000000000000,
  priceMin: 0,
  priceMax: 10000,
  peMin: 0,
  peMax: 100,
  pbMin: 0,
  pbMax: 10,
  roeMin: 0,
  roeMax: 100,
  volumeMin: 0,
  betaMin: 0,
  betaMax: 3,
  sector: 'all',
  exchange: 'all',
  assetType: 'all',
  sortBy: 'marketCap',
  sortOrder: 'desc',
};

export default function ScreenerResults() {
  const searchParams = useSearchParams();
  const [results, setResults] = useState<ScreenerResult[]>([]);
  const [loading, setLoading] = useState(false);
  // Pesos de scoring (0-100) -> normalizados internamente
  const [weights, setWeights] = useState({
    value: 30,       // P/E bajo, P/B bajo
    quality: 30,     // ROE alto
    momentum: 20,    // Cambio % reciente
    size: 20,        // Market Cap (preferencia configurable)
  });
  const [filters, setFilters] = useState<ScreenerFilters>(defaultFilters);

  // Update filters from URL params
  useEffect(() => {
    const newFilters = { ...defaultFilters };
    
    searchParams.forEach((value, key) => {
      if (key in defaultFilters) {
        const parsedValue = key.includes('Min') || key.includes('Max') || key === 'volumeMin'
          ? Number(value)
          : key === 'sortOrder'
          ? value as 'asc' | 'desc'
          : value;
        (newFilters as any)[key] = parsedValue;
      }
    });
    
    setFilters(newFilters);
  }, [searchParams]);

  const loadResults = useCallback(async () => {
    setLoading(true);
    try {
      const data = await screenStocks(filters);
      setResults(data);
    } catch (error) {
      console.error('Error loading screener results:', error);
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    // Debounce para evitar demasiadas llamadas
    const timeoutId = setTimeout(() => {
      loadResults();
    }, 300);
    
    return () => clearTimeout(timeoutId);
  }, [loadResults]);

  // Export functionality
  useEffect(() => {
    const handleExport = () => {
      if (results.length === 0) return;
      
      // Generate CSV
      const headers = ['Symbol', 'Name', 'Price', 'Change%', 'Market Cap', 'P/E', 'P/B', 'ROE%', 'Volume', 'Beta', 'Sector'];
      const rows = results.map(r => [
        r.symbol,
        `"${r.name}"`,
        r.price.toFixed(2),
        r.changePercent.toFixed(2),
        r.marketCap.toFixed(0),
        r.pe.toFixed(2),
        r.pb.toFixed(2),
        r.roe.toFixed(2),
        r.volume.toFixed(0),
        r.beta.toFixed(2),
        r.sector
      ]);
      
      const csv = [headers.join(','), ...rows.map(row => row.join(','))].join('\n');
      
      // Download file
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `screener-results-${new Date().toISOString().split('T')[0]}.csv`;
      a.click();
      window.URL.revokeObjectURL(url);
    };
    
    window.addEventListener('exportScreenerResults', handleExport);
    return () => window.removeEventListener('exportScreenerResults', handleExport);
  }, [results]);

  const formatMarketCap = (value: number) => {
    if (value >= 1000000000000) return `$${(value / 1000000000000).toFixed(2)}T`;
    if (value >= 1000000000) return `$${(value / 1000000000).toFixed(2)}B`;
    if (value >= 1000000) return `$${(value / 1000000).toFixed(2)}M`;
    return `$${value.toLocaleString()}`;
  };

  const formatVolume = (value: number) => {
    if (value >= 1000000) return `${(value / 1000000).toFixed(2)}M`;
    if (value >= 1000) return `${(value / 1000).toFixed(2)}K`;
    return value.toLocaleString();
  };

  // Normalizadores simples por percentiles aproximados (robustos sin datos históricos extensos)
  const clamp01 = (x: number) => Math.max(0, Math.min(1, x));

  const computeScore = (r: ScreenerResult) => {
    const wSum = weights.value + weights.quality + weights.momentum + weights.size;
    const wV = weights.value / wSum;
    const wQ = weights.quality / wSum;
    const wM = weights.momentum / wSum;
    const wS = weights.size / wSum;

    // Value: menor P/E y P/B mejor. Mapear P/E y P/B a 0..1 invertido.
    const peNorm = r.pe > 0 ? clamp01(1 - Math.min(r.pe, 50) / 50) : 0.5; // pe 0..50
    const pbNorm = r.pb > 0 ? clamp01(1 - Math.min(r.pb, 10) / 10) : 0.5;  // pb 0..10
    const valueScore = 0.6 * peNorm + 0.4 * pbNorm;

    // Quality: ROE más alto mejor, cap 40%
    const roeNorm = clamp01(Math.min(r.roe, 40) / 40);
    const qualityScore = roeNorm;

    // Momentum: cambio % diario como proxy (cap 10%)
    const momNorm = clamp01((Math.min(Math.max(r.changePercent, -10), 10) + 10) / 20);
    const momentumScore = momNorm;

    // Size: market cap normalizado (0..2T)
    const sizeNorm = clamp01(Math.min(r.marketCap, 2_000_000_000_000) / 2_000_000_000_000);
    const sizeScore = sizeNorm;

    const composite = wV * valueScore + wQ * qualityScore + wM * momentumScore + wS * sizeScore;
    return composite; // 0..1
  };

  const scored = results
    .map(r => ({ ...r, _score: computeScore(r) }))
    .sort((a, b) => b._score - a._score);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-6">
          <div>
            <CardTitle>Resultados del Screener</CardTitle>
            <p className="text-sm text-muted-foreground mt-1">
              {results.length} acciones encontradas
            </p>
          </div>
          <div className="w-full max-w-xl">
            <div className="grid grid-cols-4 gap-4">
              <div>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span>Value</span>
                  <span>{weights.value}</span>
                </div>
                <Slider value={[weights.value]} onValueChange={(v) => setWeights(w => ({ ...w, value: v[0] }))} max={100} step={5} />
              </div>
              <div>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span>Quality</span>
                  <span>{weights.quality}</span>
                </div>
                <Slider value={[weights.quality]} onValueChange={(v) => setWeights(w => ({ ...w, quality: v[0] }))} max={100} step={5} />
              </div>
              <div>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span>Momentum</span>
                  <span>{weights.momentum}</span>
                </div>
                <Slider value={[weights.momentum]} onValueChange={(v) => setWeights(w => ({ ...w, momentum: v[0] }))} max={100} step={5} />
              </div>
              <div>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span>Size</span>
                  <span>{weights.size}</span>
                </div>
                <Slider value={[weights.size]} onValueChange={(v) => setWeights(w => ({ ...w, size: v[0] }))} max={100} step={5} />
              </div>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="text-center py-12">
            <p className="text-muted-foreground">Cargando resultados...</p>
          </div>
        ) : results.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-muted-foreground">
              No se encontraron resultados con los criterios seleccionados
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-right">Score</TableHead>
                  <TableHead className="w-[100px]">Símbolo</TableHead>
                  <TableHead>Nombre</TableHead>
                  <TableHead className="text-right">Precio</TableHead>
                  <TableHead className="text-right">Cambio</TableHead>
                  <TableHead className="text-right">Market Cap</TableHead>
                  <TableHead className="text-right">P/E</TableHead>
                  <TableHead className="text-right">P/B</TableHead>
                  <TableHead className="text-right">ROE</TableHead>
                  <TableHead className="text-right">Volumen</TableHead>
                  <TableHead>Sector</TableHead>
                  <TableHead className="text-center">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {scored.map((stock) => {
                  const isPositive = stock.change >= 0;
                  return (
                    <TableRow key={stock.symbol} className="hover:bg-muted/50">
                      <TableCell className="text-right font-semibold">
                        {(stock._score * 100).toFixed(0)}
                      </TableCell>
                      <TableCell className="font-mono font-bold">
                        {stock.symbol}
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate">
                        {stock.name}
                      </TableCell>
                      <TableCell className="text-right font-semibold">
                        ${stock.price.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          {isPositive ? (
                            <TrendingUp className="h-4 w-4 text-green-500" />
                          ) : (
                            <TrendingDown className="h-4 w-4 text-red-500" />
                          )}
                          <span className={isPositive ? 'text-green-600' : 'text-red-600'}>
                            {isPositive ? '+' : ''}{stock.changePercent.toFixed(2)}%
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        {formatMarketCap(stock.marketCap)}
                      </TableCell>
                      <TableCell className="text-right">
                        {stock.pe.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right">
                        {stock.pb.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right">
                        <Badge variant={stock.roe > 20 ? 'default' : 'secondary'}>
                          {stock.roe.toFixed(1)}%
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        {formatVolume(stock.volume)}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-xs">
                          {stock.sector}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-center">
                        <div className="flex items-center justify-center gap-2">
                          <Link href={`/funds/${stock.symbol}`}>
                            <Button variant="ghost" size="icon" title="Ver ficha">
                              <ExternalLink className="h-4 w-4" />
                            </Button>
                          </Link>
                          <Button variant="ghost" size="icon" title="Añadir a watchlist">
                            <Star className="h-4 w-4" />
                          </Button>
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
