'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip } from 'recharts';

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

type FundHoldingsProps = {
  fundData: FundData;
};

export default function FundHoldings({ fundData }: FundHoldingsProps) {
  const { holdings } = fundData;

  if (!holdings || holdings.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Top Holdings</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">No hay datos de holdings disponibles</p>
        </CardContent>
      </Card>
    );
  }

  // Sort holdings by percentage and take top 10
  const topHoldings = holdings
    .filter(h => h.percent && h.percent > 0)
    .sort((a, b) => (b.percent || 0) - (a.percent || 0))
    .slice(0, 10);

  // Calculate total percentage of top holdings
  const totalTopPercentage = topHoldings.reduce((sum, h) => sum + (h.percent || 0), 0);

  // Prepare data for charts
  const pieData = topHoldings.map((holding, index) => ({
    name: holding.symbol || `Holding ${index + 1}`,
    value: holding.percent || 0,
    fullName: holding.name || holding.symbol || 'Unknown'
  }));

  const barData = topHoldings.map((holding, index) => ({
    symbol: holding.symbol || `H${index + 1}`,
    percentage: holding.percent || 0,
    name: holding.name || holding.symbol || 'Unknown'
  }));

  const COLORS = [
    '#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#00ff00',
    '#0088fe', '#00c49f', '#ffbb28', '#ff8042', '#8884d8'
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Top Holdings</CardTitle>
        <p className="text-sm text-muted-foreground">
          Top 10 posiciones representan el {totalTopPercentage.toFixed(1)}% del fondo
        </p>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Holdings List */}
        <div className="space-y-3">
          {topHoldings.map((holding, index) => (
            <div key={index} className="flex items-center justify-between p-3 bg-muted rounded-lg">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold">{holding.symbol}</span>
                  <Badge variant="outline" className="text-xs">
                    #{index + 1}
                  </Badge>
                </div>
                <p className="text-sm text-muted-foreground truncate">
                  {holding.name || 'Nombre no disponible'}
                </p>
              </div>
              <div className="text-right">
                <p className="font-semibold">{(holding.percent || 0).toFixed(2)}%</p>
                <Progress 
                  value={holding.percent || 0} 
                  className="w-20 h-2"
                />
              </div>
            </div>
          ))}
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Pie Chart */}
          <div>
            <h4 className="text-lg font-semibold mb-4">Distribución por Holding</h4>
            <div className="h-64">
              <ResponsiveContainer width="100%" height={300} minWidth={0} minHeight={200}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, value }) => `${name}: ${(value as number).toFixed(1)}%`}
                    outerRadius={80}
                    fill="#8884d8"
                    dataKey="value"
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => [`${value}%`, 'Porcentaje']} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Bar Chart */}
          <div>
            <h4 className="text-lg font-semibold mb-4">Top Holdings</h4>
            <div className="h-64">
              <ResponsiveContainer width="100%" height={300} minWidth={0} minHeight={200}>
                <BarChart data={barData} layout="horizontal">
                  <XAxis type="number" domain={[0, 'dataMax']} />
                  <YAxis 
                    type="category" 
                    dataKey="symbol" 
                    width={60}
                    tick={{ fontSize: 12 }}
                  />
                  <Tooltip 
                    formatter={(value) => [`${value}%`, 'Porcentaje']}
                    labelFormatter={(label, payload) => {
                      const data = payload?.[0]?.payload;
                      return data ? `${data.name} (${label})` : label;
                    }}
                  />
                  <Bar dataKey="percentage" fill="#8884d8" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Summary Stats */}
        <div className="border-t pt-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
            <div>
              <p className="text-sm text-muted-foreground">Total Holdings</p>
              <p className="text-xl font-bold">{holdings.length}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Top 10</p>
              <p className="text-xl font-bold">{totalTopPercentage.toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Mayor Holding</p>
              <p className="text-xl font-bold">{(topHoldings[0]?.percent || 0).toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Concentración</p>
              <p className="text-xl font-bold">
                {totalTopPercentage > 50 ? 'Alta' : totalTopPercentage > 30 ? 'Media' : 'Baja'}
              </p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
