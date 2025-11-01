'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useState } from 'react';
import { Edit2, Save, X } from 'lucide-react';

type FundData = {
  symbol: string;
  profile: {
    ticker?: string;
    name?: string;
    exchange?: string;
    currency?: string;
    country?: string;
    ipo?: string;
    logo?: string;
    weburl?: string;
  };
  holdings: Array<{
    symbol?: string;
    name?: string;
    percent?: number;
  }>;
  candles: {
    c: number[];
    t: number[];
    o: number[];
    h: number[];
    l: number[];
    v: number[];
  } | null;
};

type FundProfileProps = {
  fundData: FundData;
};

export default function FundProfile({ fundData }: FundProfileProps) {
  const { symbol, profile } = fundData;
  const [isEditingTER, setIsEditingTER] = useState(false);
  const [terValue, setTerValue] = useState('0.20'); // Default TER value
  const [editTerValue, setEditTerValue] = useState(terValue);

  const handleSaveTER = () => {
    setTerValue(editTerValue);
    setIsEditingTER(false);
  };

  const handleCancelTER = () => {
    setEditTerValue(terValue);
    setIsEditingTER(false);
  };

  // Calculate basic metrics
  const currentPrice = fundData.candles?.c?.[fundData.candles.c.length - 1] || 0;
  const yearHigh = Math.max(...(fundData.candles?.h || [0]));
  const yearLow = Math.min(...(fundData.candles?.l || [currentPrice]));
  const avgVolume = fundData.candles?.v ? 
    fundData.candles.v.reduce((a, b) => a + b, 0) / fundData.candles.v.length : 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Perfil del Fondo</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Basic Information */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <div>
              <Label className="text-sm font-medium text-muted-foreground">Nombre</Label>
              <p className="text-lg font-semibold">{profile.name || 'N/A'}</p>
            </div>
            <div>
              <Label className="text-sm font-medium text-muted-foreground">Símbolo</Label>
              <p className="text-lg font-mono">{symbol}</p>
            </div>
            <div>
              <Label className="text-sm font-medium text-muted-foreground">Exchange</Label>
              <p className="text-lg">{profile.exchange || 'N/A'}</p>
            </div>
            <div>
              <Label className="text-sm font-medium text-muted-foreground">Moneda</Label>
              <p className="text-lg">{profile.currency || 'USD'}</p>
            </div>
          </div>
          
          <div className="space-y-4">
            <div>
              <Label className="text-sm font-medium text-muted-foreground">País</Label>
              <p className="text-lg">{profile.country || 'N/A'}</p>
            </div>
            <div>
              <Label className="text-sm font-medium text-muted-foreground">Fecha de Lanzamiento</Label>
              <p className="text-lg">
                {profile.ipo ? new Date(profile.ipo).toLocaleDateString() : 'N/A'}
              </p>
            </div>
            <div>
              <Label className="text-sm font-medium text-muted-foreground">TER (Comisión Anual)</Label>
              <div className="flex items-center gap-2">
                {isEditingTER ? (
                  <div className="flex items-center gap-2">
                    <Input
                      type="number"
                      step="0.01"
                      value={editTerValue}
                      onChange={(e) => setEditTerValue(e.target.value)}
                      className="w-20"
                    />
                    <span className="text-sm text-muted-foreground">%</span>
                    <Button size="sm" onClick={handleSaveTER}>
                      <Save className="h-4 w-4" />
                    </Button>
                    <Button size="sm" variant="outline" onClick={handleCancelTER}>
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <span className="text-lg font-semibold">{terValue}%</span>
                    <Button size="sm" variant="ghost" onClick={() => setIsEditingTER(true)}>
                      <Edit2 className="h-4 w-4" />
                    </Button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Market Data */}
        <div className="border-t pt-6">
          <h3 className="text-lg font-semibold mb-4">Datos de Mercado</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center p-4 bg-muted rounded-lg">
              <p className="text-sm text-muted-foreground">Precio Actual</p>
              <p className="text-xl font-bold">${currentPrice.toFixed(2)}</p>
            </div>
            <div className="text-center p-4 bg-muted rounded-lg">
              <p className="text-sm text-muted-foreground">Máximo 52W</p>
              <p className="text-xl font-bold">${yearHigh.toFixed(2)}</p>
            </div>
            <div className="text-center p-4 bg-muted rounded-lg">
              <p className="text-sm text-muted-foreground">Mínimo 52W</p>
              <p className="text-xl font-bold">${yearLow.toFixed(2)}</p>
            </div>
            <div className="text-center p-4 bg-muted rounded-lg">
              <p className="text-sm text-muted-foreground">Vol. Promedio</p>
              <p className="text-xl font-bold">{Math.round(avgVolume).toLocaleString()}</p>
            </div>
          </div>
        </div>

        {/* Fund Type & Strategy */}
        <div className="border-t pt-6">
          <h3 className="text-lg font-semibold mb-4">Tipo de Fondo</h3>
          <div className="flex flex-wrap gap-2">
            <Badge variant="secondary">ETF</Badge>
            <Badge variant="outline">Indexado</Badge>
            <Badge variant="outline">Pasivo</Badge>
            {profile.country && (
              <Badge variant="outline">{profile.country}</Badge>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
