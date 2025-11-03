'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Search, X } from 'lucide-react';

type FilterCriteria = {
  // Básicos
  marketCapMin: number;
  marketCapMax: number;
  priceMin: number;
  priceMax: number;
  
  // Fundamentales
  peMin: number;
  peMax: number;
  pbMin: number;
  pbMax: number;
  roeMin: number;
  roeMax: number;
  
  // Técnicos
  volumeMin: number;
  betaMin: number;
  betaMax: number;
  
  // Categorías
  sector: string;
  exchange: string;
  assetType: string;
  
  // Ordenamiento
  sortBy: string;
  sortOrder: 'asc' | 'desc';
};

export const defaultFilters: FilterCriteria = {
  marketCapMin: 0,
  marketCapMax: 1000000000000, // 1T
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

const sectors = [
  'all', 'Technology', 'Healthcare', 'Financial Services', 'Consumer Discretionary',
  'Industrials', 'Consumer Staples', 'Energy', 'Utilities', 'Real Estate',
  'Materials', 'Communication Services'
];

const exchanges = [
  'all', 'NASDAQ', 'NYSE', 'AMEX', 'OTC'
];

const assetTypes = [
  'all', 'Stock', 'ETF', 'REIT', 'ADR'
];

const sortOptions = [
  { value: 'marketCap', label: 'Market Cap' },
  { value: 'price', label: 'Precio' },
  { value: 'pe', label: 'P/E Ratio' },
  { value: 'pb', label: 'P/B Ratio' },
  { value: 'roe', label: 'ROE' },
  { value: 'volume', label: 'Volumen' },
  { value: 'beta', label: 'Beta' },
  { value: 'name', label: 'Nombre' },
];

export default function ScreenerFilters() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [filters, setFilters] = useState<FilterCriteria>(defaultFilters);
  const [activeFilters, setActiveFilters] = useState<string[]>([]);

  // Load filters from URL on mount
  useEffect(() => {
    const newFilters = { ...defaultFilters };
    let hasActiveFilters = false;
    
    searchParams.forEach((value, key) => {
      if (key in defaultFilters) {
        const parsedValue = key.includes('Min') || key.includes('Max') || key.includes('Min') || key === 'volumeMin' 
          ? Number(value) 
          : value;
        (newFilters as any)[key] = parsedValue;
        
        // Check if filter is different from default
        if (JSON.stringify(parsedValue) !== JSON.stringify((defaultFilters as any)[key])) {
          hasActiveFilters = true;
        }
      }
    });
    
    setFilters(newFilters);
    if (hasActiveFilters) {
      updateActiveFilters(newFilters);
    }
  }, []);

  const updateActiveFilters = (currentFilters: FilterCriteria) => {
    const active: string[] = [];
    Object.keys(currentFilters).forEach(key => {
      const filterKey = key as keyof FilterCriteria;
      if (JSON.stringify(currentFilters[filterKey]) !== JSON.stringify(defaultFilters[filterKey])) {
        active.push(key);
      }
    });
    setActiveFilters(active);
  };

  const updateFilter = (key: keyof FilterCriteria, value: any) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  const resetFilters = () => {
    setFilters(defaultFilters);
    setActiveFilters([]);
    router.push('/screener');
  };

  const applyFilters = () => {
    // Build URL search params from filters
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      // Only add if different from default
      if (JSON.stringify(value) !== JSON.stringify((defaultFilters as any)[key])) {
        params.set(key, String(value));
      }
    });
    
    updateActiveFilters(filters);
    router.push(`/screener?${params.toString()}`);
  };

  const removeFilter = (filterKey: string) => {
    const key = filterKey as keyof FilterCriteria;
    if (key in defaultFilters) {
      const newFilters = { ...filters, [key]: defaultFilters[key] };
      setFilters(newFilters);
      
      // Update URL
      const params = new URLSearchParams();
      Object.entries(newFilters).forEach(([k, value]) => {
        if (JSON.stringify(value) !== JSON.stringify((defaultFilters as any)[k])) {
          params.set(k, String(value));
        }
      });
      
      setActiveFilters(prev => prev.filter(f => f !== filterKey));
      router.push(`/screener?${params.toString()}`);
    }
  };

  const formatMarketCap = (value: number) => {
    if (value >= 1000000000) return `$${(value / 1000000000).toFixed(1)}B`;
    if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
    return `$${value.toLocaleString()}`;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <CardTitle className="text-lg">Filtros</CardTitle>
        <Button variant="ghost" size="sm" onClick={resetFilters}>
          <X className="h-4 w-4 mr-1" />
          Limpiar
        </Button>
      </div>

      {/* Filtros activos */}
      {activeFilters.length > 0 && (
        <div className="space-y-2">
          <Label className="text-sm font-medium">Filtros Activos</Label>
          <div className="flex flex-wrap gap-2">
            {activeFilters.map(filter => (
              <Badge key={filter} variant="secondary" className="flex items-center gap-1">
                {filter}
                <X 
                  className="h-3 w-3 cursor-pointer" 
                  onClick={() => removeFilter(filter)}
                />
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* Market Cap */}
      <div className="space-y-3">
        <Label className="text-sm font-medium">Market Cap</Label>
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Input
              type="number"
              placeholder="Min"
              value={filters.marketCapMin}
              onChange={(e) => updateFilter('marketCapMin', Number(e.target.value))}
              className="text-sm"
            />
            <span className="text-sm text-muted-foreground">-</span>
            <Input
              type="number"
              placeholder="Max"
              value={filters.marketCapMax}
              onChange={(e) => updateFilter('marketCapMax', Number(e.target.value))}
              className="text-sm"
            />
          </div>
          <div className="text-xs text-muted-foreground">
            {formatMarketCap(filters.marketCapMin)} - {formatMarketCap(filters.marketCapMax)}
          </div>
        </div>
      </div>

      {/* Precio */}
      <div className="space-y-3">
        <Label className="text-sm font-medium">Precio</Label>
        <div className="flex items-center gap-2">
          <Input
            type="number"
            placeholder="Min"
            value={filters.priceMin}
            onChange={(e) => updateFilter('priceMin', Number(e.target.value))}
            className="text-sm"
          />
          <span className="text-sm text-muted-foreground">-</span>
          <Input
            type="number"
            placeholder="Max"
            value={filters.priceMax}
            onChange={(e) => updateFilter('priceMax', Number(e.target.value))}
            className="text-sm"
          />
        </div>
      </div>

      {/* P/E Ratio */}
      <div className="space-y-3">
        <Label className="text-sm font-medium">P/E Ratio</Label>
        <div className="flex items-center gap-2">
          <Input
            type="number"
            placeholder="Min"
            value={filters.peMin}
            onChange={(e) => updateFilter('peMin', Number(e.target.value))}
            className="text-sm"
          />
          <span className="text-sm text-muted-foreground">-</span>
          <Input
            type="number"
            placeholder="Max"
            value={filters.peMax}
            onChange={(e) => updateFilter('peMax', Number(e.target.value))}
            className="text-sm"
          />
        </div>
      </div>

      {/* P/B Ratio */}
      <div className="space-y-3">
        <Label className="text-sm font-medium">P/B Ratio</Label>
        <div className="flex items-center gap-2">
          <Input
            type="number"
            placeholder="Min"
            value={filters.pbMin}
            onChange={(e) => updateFilter('pbMin', Number(e.target.value))}
            className="text-sm"
          />
          <span className="text-sm text-muted-foreground">-</span>
          <Input
            type="number"
            placeholder="Max"
            value={filters.pbMax}
            onChange={(e) => updateFilter('pbMax', Number(e.target.value))}
            className="text-sm"
          />
        </div>
      </div>

      {/* ROE */}
      <div className="space-y-3">
        <Label className="text-sm font-medium">ROE (%)</Label>
        <div className="flex items-center gap-2">
          <Input
            type="number"
            placeholder="Min"
            value={filters.roeMin}
            onChange={(e) => updateFilter('roeMin', Number(e.target.value))}
            className="text-sm"
          />
          <span className="text-sm text-muted-foreground">-</span>
          <Input
            type="number"
            placeholder="Max"
            value={filters.roeMax}
            onChange={(e) => updateFilter('roeMax', Number(e.target.value))}
            className="text-sm"
          />
        </div>
      </div>

      {/* Sector */}
      <div className="space-y-3">
        <Label className="text-sm font-medium">Sector</Label>
        <Select value={filters.sector} onValueChange={(value) => updateFilter('sector', value)}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {sectors.map(sector => (
              <SelectItem key={sector} value={sector}>
                {sector === 'all' ? 'Todos los sectores' : sector}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Exchange */}
      <div className="space-y-3">
        <Label className="text-sm font-medium">Exchange</Label>
        <Select value={filters.exchange} onValueChange={(value) => updateFilter('exchange', value)}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {exchanges.map(exchange => (
              <SelectItem key={exchange} value={exchange}>
                {exchange === 'all' ? 'Todas las exchanges' : exchange}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Asset Type */}
      <div className="space-y-3">
        <Label className="text-sm font-medium">Tipo de Activo</Label>
        <Select value={filters.assetType} onValueChange={(value) => updateFilter('assetType', value)}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {assetTypes.map(type => (
              <SelectItem key={type} value={type}>
                {type === 'all' ? 'Todos los tipos' : type}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Ordenamiento */}
      <div className="space-y-3">
        <Label className="text-sm font-medium">Ordenar por</Label>
        <div className="space-y-2">
          <Select value={filters.sortBy} onValueChange={(value) => updateFilter('sortBy', value)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {sortOptions.map(option => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          
          <Select value={filters.sortOrder} onValueChange={(value: 'asc' | 'desc') => updateFilter('sortOrder', value)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="desc">Descendente</SelectItem>
              <SelectItem value="asc">Ascendente</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Botón de búsqueda */}
      <Button onClick={applyFilters} className="w-full">
        <Search className="h-4 w-4 mr-2" />
        Buscar
      </Button>
    </div>
  );
}
