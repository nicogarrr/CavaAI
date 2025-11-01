'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { TrendingUp, TrendingDown, Plus, Minus, RotateCcw, AlertTriangle } from 'lucide-react';
import { getRebalancingRecommendations } from '@/lib/actions/correlation.actions';

type RebalancingSuggestionsProps = {
  positions: Array<{
    symbol: string;
    percentage: number;
    sector?: string;
  }>;
};

type RebalancingRecommendation = {
  type: 'reduce' | 'increase' | 'add' | 'remove';
  symbol: string;
  currentWeight: number;
  recommendedWeight: number;
  reason: string;
};

export default function RebalancingSuggestions({ positions }: RebalancingSuggestionsProps) {
  const [recommendations, setRecommendations] = useState<RebalancingRecommendation[]>([]);
  const [loading, setLoading] = useState(false);

  const loadRecommendations = async () => {
    if (positions.length === 0) return;
    
    setLoading(true);
    try {
      const data = await getRebalancingRecommendations(positions);
      setRecommendations(data);
    } catch (error) {
      console.error('Error loading rebalancing recommendations:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRecommendations();
  }, [positions]);

  const getRecommendationIcon = (type: string) => {
    switch (type) {
      case 'reduce': return <Minus className="h-4 w-4 text-red-500" />;
      case 'increase': return <Plus className="h-4 w-4 text-green-500" />;
      case 'add': return <Plus className="h-4 w-4 text-blue-500" />;
      case 'remove': return <Minus className="h-4 w-4 text-orange-500" />;
      default: return <RotateCcw className="h-4 w-4" />;
    }
  };

  const getRecommendationColor = (type: string) => {
    switch (type) {
      case 'reduce': return 'text-red-600';
      case 'increase': return 'text-green-600';
      case 'add': return 'text-blue-600';
      case 'remove': return 'text-orange-600';
      default: return 'text-gray-600';
    }
  };

  const getRecommendationBadge = (type: string) => {
    switch (type) {
      case 'reduce': return <Badge variant="destructive" className="text-xs">Reducir</Badge>;
      case 'increase': return <Badge variant="default" className="text-xs">Aumentar</Badge>;
      case 'add': return <Badge variant="secondary" className="text-xs">Añadir</Badge>;
      case 'remove': return <Badge variant="outline" className="text-xs">Eliminar</Badge>;
      default: return <Badge variant="outline" className="text-xs">Ajustar</Badge>;
    }
  };

  const calculateImpact = (current: number, recommended: number) => {
    const change = recommended - current;
    const changePercent = (change / current) * 100;
    return { change, changePercent };
  };

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Recomendaciones de Rebalanceo</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Analizando recomendaciones...</p>
        </CardContent>
      </Card>
    );
  }

  if (recommendations.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <RotateCcw className="h-5 w-5" />
            Recomendaciones de Rebalanceo
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8">
            <div className="w-16 h-16 bg-green-100 dark:bg-green-900 rounded-full flex items-center justify-center mx-auto mb-4">
              <TrendingUp className="h-8 w-8 text-green-600" />
            </div>
            <h3 className="text-lg font-semibold mb-2">Portfolio Bien Balanceado</h3>
            <p className="text-muted-foreground">
              Tu portfolio está bien diversificado. No se requieren cambios inmediatos.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <RotateCcw className="h-5 w-5" />
          Recomendaciones de Rebalanceo
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Sugerencias basadas en análisis de correlación y diversificación
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Resumen de recomendaciones */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="text-center p-3 bg-red-50 dark:bg-red-950 rounded-lg">
            <p className="text-sm text-muted-foreground">Reducir</p>
            <p className="text-xl font-bold text-red-600">
              {recommendations.filter(r => r.type === 'reduce').length}
            </p>
          </div>
          <div className="text-center p-3 bg-green-50 dark:bg-green-950 rounded-lg">
            <p className="text-sm text-muted-foreground">Aumentar</p>
            <p className="text-xl font-bold text-green-600">
              {recommendations.filter(r => r.type === 'increase').length}
            </p>
          </div>
          <div className="text-center p-3 bg-blue-50 dark:bg-blue-950 rounded-lg">
            <p className="text-sm text-muted-foreground">Añadir</p>
            <p className="text-xl font-bold text-blue-600">
              {recommendations.filter(r => r.type === 'add').length}
            </p>
          </div>
          <div className="text-center p-3 bg-orange-50 dark:bg-orange-950 rounded-lg">
            <p className="text-sm text-muted-foreground">Eliminar</p>
            <p className="text-xl font-bold text-orange-600">
              {recommendations.filter(r => r.type === 'remove').length}
            </p>
          </div>
        </div>

        {/* Lista de recomendaciones */}
        <div className="space-y-3">
          {recommendations.map((recommendation, index) => {
            const { change, changePercent } = calculateImpact(
              recommendation.currentWeight, 
              recommendation.recommendedWeight
            );
            
            return (
              <div
                key={index}
                className="flex items-center justify-between p-4 rounded-lg border hover:bg-muted/50"
              >
                <div className="flex items-center gap-3">
                  {getRecommendationIcon(recommendation.type)}
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{recommendation.symbol}</span>
                      {getRecommendationBadge(recommendation.type)}
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">
                      {recommendation.reason}
                    </p>
                  </div>
                </div>
                
                <div className="text-right">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm text-muted-foreground">Actual:</span>
                    <span className="font-medium">
                      {(recommendation.currentWeight * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm text-muted-foreground">Recomendado:</span>
                    <span className={`font-bold ${getRecommendationColor(recommendation.type)}`}>
                      {(recommendation.recommendedWeight * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-muted-foreground">Cambio:</span>
                    <span className={`font-semibold ${
                      change > 0 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {change > 0 ? '+' : ''}{(change * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Acciones sugeridas */}
        <div className="border-t pt-4">
          <h4 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5" />
            Acciones Recomendadas
          </h4>
          
          <div className="space-y-3">
            {recommendations.filter(r => r.type === 'reduce').length > 0 && (
              <div className="p-3 bg-red-50 dark:bg-red-950 rounded-lg">
                <p className="text-sm font-medium text-red-800 dark:text-red-200 mb-2">
                  🔴 Reducir Exposición
                </p>
                <p className="text-xs text-red-600 dark:text-red-400">
                  Considera vender parcialmente activos con alta correlación o sobreponderación sectorial.
                </p>
              </div>
            )}
            
            {recommendations.filter(r => r.type === 'increase').length > 0 && (
              <div className="p-3 bg-green-50 dark:bg-green-950 rounded-lg">
                <p className="text-sm font-medium text-green-800 dark:text-green-200 mb-2">
                  🟢 Aumentar Exposición
                </p>
                <p className="text-xs text-green-600 dark:text-green-400">
                  Aumenta la ponderación de activos con baja correlación o subponderación.
                </p>
              </div>
            )}
            
            {recommendations.filter(r => r.type === 'add').length > 0 && (
              <div className="p-3 bg-blue-50 dark:bg-blue-950 rounded-lg">
                <p className="text-sm font-medium text-blue-800 dark:text-blue-200 mb-2">
                  🔵 Añadir Nuevos Activos
                </p>
                <p className="text-xs text-blue-600 dark:text-blue-400">
                  Considera añadir activos de sectores o regiones subrepresentados.
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Botón de acción */}
        <div className="flex justify-center pt-4">
          <Button className="flex items-center gap-2">
            <RotateCcw className="h-4 w-4" />
            Aplicar Rebalanceo Sugerido
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
