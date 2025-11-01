'use client';

import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Wifi, WifiOff, AlertTriangle, CheckCircle, Info } from 'lucide-react';

type PortfolioStatusProps = {
  hasApiKey: boolean;
  isOnline: boolean;
  mockDataCount: number;
  totalPositions: number;
};

export default function PortfolioStatus({ 
  hasApiKey, 
  isOnline, 
  mockDataCount, 
  totalPositions 
}: PortfolioStatusProps) {
  const isUsingMockData = mockDataCount > 0;
  const allDataMock = mockDataCount === totalPositions;

  if (!hasApiKey) {
    return (
      <Card className="mb-4 border-orange-200 bg-orange-50">
        <CardContent className="p-4">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-orange-600" />
            <span className="text-sm font-medium text-orange-800">
              Modo Demo: No hay API key configurada. Se están usando datos simulados.
            </span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!isOnline) {
    return (
      <Card className="mb-4 border-red-200 bg-red-50">
        <CardContent className="p-4">
          <div className="flex items-center gap-2">
            <WifiOff className="h-4 w-4 text-red-600" />
            <span className="text-sm font-medium text-red-800">
              Sin conexión: Se están usando datos simulados.
            </span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (isUsingMockData && mockDataCount < totalPositions) {
    // Solo mostrar si hay algunas posiciones con datos reales (no todas simuladas)
    // Mensaje más positivo y menos alarmante
    return (
      <Card className="mb-4 border-blue-200 bg-blue-50/50">
        <CardContent className="p-4">
          <div className="flex items-center gap-2">
            <Info className="h-4 w-4 text-blue-600" />
            <span className="text-sm text-blue-700">
              {totalPositions - mockDataCount} de {totalPositions} posiciones actualizadas.
              {mockDataCount > 0 && ` Algunas posiciones pueden mostrar precios estimados temporalmente.`}
            </span>
          </div>
        </CardContent>
      </Card>
    );
  }
  
  // Si todas son mock data y hay API key, mostrar mensaje diferente
  if (allDataMock && hasApiKey) {
    return (
      <Card className="mb-4 border-yellow-200 bg-yellow-50/50">
        <CardContent className="p-4">
          <div className="flex items-center gap-2">
            <Info className="h-4 w-4 text-yellow-600" />
            <span className="text-sm text-yellow-700">
              Actualizando precios... Esto puede tardar unos momentos.
            </span>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Si todo está bien, no mostrar nada
  return null;
}

