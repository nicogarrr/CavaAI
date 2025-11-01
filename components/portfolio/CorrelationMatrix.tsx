'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { AlertTriangle, TrendingUp, TrendingDown, Info } from 'lucide-react';
import { calculateCorrelationMatrix, CorrelationData } from '@/lib/actions/correlation.actions';

type CorrelationMatrixProps = {
  symbols: string[];
};

export default function CorrelationMatrix({ symbols }: CorrelationMatrixProps) {
  const [correlations, setCorrelations] = useState<CorrelationData[]>([]);
  const [loading, setLoading] = useState(false);
  const [period, setPeriod] = useState<'90' | '180' | '252'>('90');
  const [sortBy, setSortBy] = useState<'correlation' | 'significance'>('correlation');

  const loadCorrelations = async () => {
    if (symbols.length < 2) return;
    
    setLoading(true);
    try {
      const data = await calculateCorrelationMatrix(symbols, parseInt(period));
      setCorrelations(data);
    } catch (error) {
      console.error('Error loading correlations:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCorrelations();
  }, [symbols, period]);

  const getCorrelationColor = (correlation: number) => {
    const abs = Math.abs(correlation);
    if (abs > 0.7) return 'bg-red-500';
    if (abs > 0.4) return 'bg-yellow-500';
    if (abs > 0.2) return 'bg-blue-500';
    return 'bg-green-500';
  };

  const getCorrelationIntensity = (correlation: number) => {
    const abs = Math.abs(correlation);
    if (abs > 0.8) return 1;
    if (abs > 0.6) return 0.8;
    if (abs > 0.4) return 0.6;
    if (abs > 0.2) return 0.4;
    return 0.2;
  };

  const sortedCorrelations = [...correlations].sort((a, b) => {
    if (sortBy === 'correlation') {
      return Math.abs(b.correlation) - Math.abs(a.correlation);
    }
    return a.significance === 'high' ? -1 : b.significance === 'high' ? 1 : 0;
  });

  const highCorrelations = correlations.filter(c => Math.abs(c.correlation) > 0.7);
  const lowCorrelations = correlations.filter(c => Math.abs(c.correlation) < 0.3);
  const negativeCorrelations = correlations.filter(c => c.correlation < -0.3);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5" />
            Matriz de Correlación
          </CardTitle>
          <div className="flex items-center gap-2">
            <Select value={period} onValueChange={(value: '90' | '180' | '252') => setPeriod(value)}>
              <SelectTrigger className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="90">3 meses</SelectItem>
                <SelectItem value="180">6 meses</SelectItem>
                <SelectItem value="252">1 año</SelectItem>
              </SelectContent>
            </Select>
            <Select value={sortBy} onValueChange={(value: 'correlation' | 'significance') => setSortBy(value)}>
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="correlation">Por correlación</SelectItem>
                <SelectItem value="significance">Por significancia</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Resumen de correlaciones */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="text-center p-4 bg-red-50 dark:bg-red-950 rounded-lg">
            <div className="flex items-center justify-center gap-2 mb-2">
              <AlertTriangle className="h-5 w-5 text-red-500" />
              <span className="font-semibold text-red-700 dark:text-red-300">Alta Correlación</span>
            </div>
            <p className="text-2xl font-bold text-red-600">{highCorrelations.length}</p>
            <p className="text-sm text-red-600">&gt; 70%</p>
          </div>
          
          <div className="text-center p-4 bg-green-50 dark:bg-green-950 rounded-lg">
            <div className="flex items-center justify-center gap-2 mb-2">
              <TrendingDown className="h-5 w-5 text-green-500" />
              <span className="font-semibold text-green-700 dark:text-green-300">Baja Correlación</span>
            </div>
            <p className="text-2xl font-bold text-green-600">{lowCorrelations.length}</p>
            <p className="text-sm text-green-600">&lt; 30%</p>
          </div>
          
          <div className="text-center p-4 bg-blue-50 dark:bg-blue-950 rounded-lg">
            <div className="flex items-center justify-center gap-2 mb-2">
              <TrendingUp className="h-5 w-5 text-blue-500" />
              <span className="font-semibold text-blue-700 dark:text-blue-300">Correlación Negativa</span>
            </div>
            <p className="text-2xl font-bold text-blue-600">{negativeCorrelations.length}</p>
            <p className="text-sm text-blue-600">&lt; -30%</p>
          </div>
        </div>

        {/* Matriz visual */}
        {loading ? (
          <div className="text-center py-8">
            <p className="text-muted-foreground">Calculando correlaciones...</p>
          </div>
        ) : correlations.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-muted-foreground">No hay suficientes datos para calcular correlaciones</p>
          </div>
        ) : (
          <div className="space-y-4">
            <h4 className="text-lg font-semibold">Pares de Activos</h4>
            <div className="grid gap-2">
              {sortedCorrelations.map((correlation, index) => {
                const intensity = getCorrelationIntensity(correlation.correlation);
                const colorClass = getCorrelationColor(correlation.correlation);
                
                return (
                  <div
                    key={`${correlation.symbol1}-${correlation.symbol2}`}
                    className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50"
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-4 h-4 rounded ${colorClass}`}
                        style={{ opacity: intensity }}
                      />
                      <span className="font-medium">
                        {correlation.symbol1} ↔ {correlation.symbol2}
                      </span>
                      <Badge 
                        variant={correlation.significance === 'high' ? 'destructive' : 
                                correlation.significance === 'medium' ? 'secondary' : 'outline'}
                        className="text-xs"
                      >
                        {correlation.significance === 'high' ? 'Alta' : 
                         correlation.significance === 'medium' ? 'Media' : 'Baja'}
                      </Badge>
                    </div>
                    
                    <div className="text-right">
                      <p className={`font-bold ${
                        Math.abs(correlation.correlation) > 0.7 ? 'text-red-600' :
                        Math.abs(correlation.correlation) > 0.4 ? 'text-yellow-600' :
                        Math.abs(correlation.correlation) > 0.2 ? 'text-blue-600' : 'text-green-600'
                      }`}>
                        {(correlation.correlation * 100).toFixed(1)}%
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {correlation.period}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Insights y recomendaciones */}
        {correlations.length > 0 && (
          <div className="border-t pt-4">
            <h4 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Info className="h-5 w-5" />
              Insights de Diversificación
            </h4>
            
            <div className="space-y-3">
              {highCorrelations.length > 0 && (
                <div className="p-3 bg-red-50 dark:bg-red-950 rounded-lg">
                  <p className="text-sm font-medium text-red-800 dark:text-red-200">
                    ⚠️ {highCorrelations.length} pares con alta correlación
                  </p>
                  <p className="text-xs text-red-600 dark:text-red-400 mt-1">
                    Considera reducir la exposición a activos altamente correlacionados para mejorar la diversificación.
                  </p>
                </div>
              )}
              
              {lowCorrelations.length > 0 && (
                <div className="p-3 bg-green-50 dark:bg-green-950 rounded-lg">
                  <p className="text-sm font-medium text-green-800 dark:text-green-200">
                    ✅ {lowCorrelations.length} pares con baja correlación
                  </p>
                  <p className="text-xs text-green-600 dark:text-green-400 mt-1">
                    Excelente diversificación: estos activos proporcionan buena diversificación.
                  </p>
                </div>
              )}
              
              {negativeCorrelations.length > 0 && (
                <div className="p-3 bg-blue-50 dark:bg-blue-950 rounded-lg">
                  <p className="text-sm font-medium text-blue-800 dark:text-blue-200">
                    🎯 {negativeCorrelations.length} pares con correlación negativa
                  </p>
                  <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">
                    Activos con correlación negativa proporcionan excelente diversificación y reducción de riesgo.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
