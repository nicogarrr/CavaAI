'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { Filter, X } from 'lucide-react';

export interface ProPicksFilters {
  timePeriod: 'week' | 'month' | 'quarter' | 'year';
  limit: number;
  minScore: number;
  sector: string;
  sortBy: 'score' | 'momentum' | 'value' | 'growth' | 'profitability';
}

interface Props {
  filters: ProPicksFilters;
  onFiltersChange: (filters: ProPicksFilters) => void;
  onApply: () => void;
}

const sectors = [
  'all',
  'Technology',
  'Healthcare',
  'Financial Services',
  'Consumer Discretionary',
  'Industrials',
  'Consumer Staples',
  'Energy',
  'Utilities',
  'Real Estate',
  'Materials',
  'Communication Services'
];

export default function EnhancedProPicksFilters({ filters, onFiltersChange, onApply }: Props) {
  const updateFilter = <K extends keyof ProPicksFilters>(key: K, value: ProPicksFilters[K]) => {
    onFiltersChange({ ...filters, [key]: value });
  };

  const resetFilters = () => {
    onFiltersChange({
      timePeriod: 'month',
      limit: 20,
      minScore: 70,
      sector: 'all',
      sortBy: 'score',
    });
  };

  return (
    <Card className="border-gray-700 bg-gray-800/50">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Filter className="h-5 w-5 text-teal-400" />
            <CardTitle className="text-lg">Filtros Avanzados</CardTitle>
          </div>
          <Button variant="ghost" size="sm" onClick={resetFilters}>
            <X className="h-4 w-4 mr-1" />
            Limpiar
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Período de Tiempo */}
        <div className="space-y-3">
          <Label className="text-sm font-medium text-gray-200">Período de Rendimiento</Label>
          <Select 
            value={filters.timePeriod} 
            onValueChange={(value: ProPicksFilters['timePeriod']) => updateFilter('timePeriod', value)}
          >
            <SelectTrigger className="bg-gray-900 border-gray-700">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="week">Última Semana</SelectItem>
              <SelectItem value="month">Último Mes</SelectItem>
              <SelectItem value="quarter">Último Trimestre</SelectItem>
              <SelectItem value="year">Último Año</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-xs text-gray-500">
            Evalúa el rendimiento de las acciones en el período seleccionado
          </p>
        </div>

        {/* Cantidad de Resultados */}
        <div className="space-y-3">
          <Label className="text-sm font-medium text-gray-200">
            Cantidad de Acciones: {filters.limit}
          </Label>
          <Slider
            value={[filters.limit]}
            onValueChange={(value) => updateFilter('limit', value[0])}
            min={5}
            max={50}
            step={5}
            className="py-2"
          />
          <div className="flex justify-between text-xs text-gray-500">
            <span>5</span>
            <span>50</span>
          </div>
        </div>

        {/* Score Mínimo */}
        <div className="space-y-3">
          <Label className="text-sm font-medium text-gray-200">
            Score Mínimo: {filters.minScore}
          </Label>
          <Slider
            value={[filters.minScore]}
            onValueChange={(value) => updateFilter('minScore', value[0])}
            min={50}
            max={95}
            step={5}
            className="py-2"
          />
          <div className="flex justify-between text-xs text-gray-500">
            <span>50 (Aceptable)</span>
            <span>95 (Excelente)</span>
          </div>
        </div>

        {/* Sector */}
        <div className="space-y-3">
          <Label className="text-sm font-medium text-gray-200">Sector</Label>
          <Select 
            value={filters.sector} 
            onValueChange={(value) => updateFilter('sector', value)}
          >
            <SelectTrigger className="bg-gray-900 border-gray-700">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {sectors.map(sector => (
                <SelectItem key={sector} value={sector}>
                  {sector === 'all' ? 'Todos los Sectores' : sector}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Ordenar por */}
        <div className="space-y-3">
          <Label className="text-sm font-medium text-gray-200">Ordenar por</Label>
          <Select 
            value={filters.sortBy} 
            onValueChange={(value: ProPicksFilters['sortBy']) => updateFilter('sortBy', value)}
          >
            <SelectTrigger className="bg-gray-900 border-gray-700">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="score">Score General</SelectItem>
              <SelectItem value="momentum">Momentum</SelectItem>
              <SelectItem value="value">Valor</SelectItem>
              <SelectItem value="growth">Crecimiento</SelectItem>
              <SelectItem value="profitability">Rentabilidad</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Botón Aplicar */}
        <Button onClick={onApply} className="w-full bg-teal-600 hover:bg-teal-700">
          <Filter className="h-4 w-4 mr-2" />
          Aplicar Filtros
        </Button>
      </CardContent>
    </Card>
  );
}
