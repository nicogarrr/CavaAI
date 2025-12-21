'use client';

import { useMemo } from 'react';
import { Card } from '@/components/ui/card';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, LineChart, Line, PieChart, Pie, Cell } from 'recharts';
import { extractTableData, tableToChartData, TableData } from '@/lib/utils/tableExtractor';

interface TableVisualizationProps {
    tableMarkdown: string;
    title?: string;
    chartType?: 'bar' | 'line' | 'pie';
}

const COLORS = [
    '#0FEDBE', '#5862FF', '#FDD458', '#FF495B', '#FF8243', 
    '#D13BFF', '#0FEDBE', '#5862FF', '#FDD458', '#FF495B'
];

export default function TableVisualization({ 
    tableMarkdown, 
    title = 'Visualización de Datos',
    chartType = 'bar'
}: TableVisualizationProps) {
    const { tableData, chartData } = useMemo(() => {
        const data = extractTableData(tableMarkdown);
        if (!data || data.rows.length === 0) {
            return { tableData: null, chartData: [] };
        }
        
        // Intentar determinar qué columnas usar para el gráfico
        // Buscar columnas con valores numéricos
        let xIndex = 0; // Primera columna suele ser categoría
        let yIndex = 1; // Segunda columna suele ser valor
        
        // Buscar columnas con nombres que sugieran valores numéricos
        for (let i = 0; i < data.headers.length; i++) {
            const header = data.headers[i].toLowerCase();
            if (header.includes('ingreso') || header.includes('revenue') || 
                header.includes('valor') || header.includes('value') ||
                header.includes('precio') || header.includes('price') ||
                header.includes('%') || header.includes('porcentaje') ||
                header.includes('crecimiento') || header.includes('growth')) {
                yIndex = i;
                break;
            }
        }
        
        // Si la primera columna parece ser una fecha/año, usarla para X
        if (data.headers.length > 0) {
            const firstHeader = data.headers[0].toLowerCase();
            if (firstHeader.includes('año') || firstHeader.includes('year') ||
                firstHeader.includes('fecha') || firstHeader.includes('date') ||
                firstHeader.includes('periodo') || firstHeader.includes('period')) {
                xIndex = 0;
            }
        }
        
        const chartDataResult = tableToChartData(data, xIndex, yIndex);
        
        return { tableData: data, chartData: chartDataResult };
    }, [tableMarkdown]);
    
    if (!tableData || chartData.length === 0) {
        return null;
    }
    
    return (
        <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50 mt-6">
            <h3 className="text-lg font-semibold mb-4 text-gray-200">{title}</h3>
            
            <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                    {chartType === 'bar' && (
                        <BarChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis 
                                dataKey="name" 
                                stroke="#9CA3AF"
                                fontSize={12}
                                angle={-45}
                                textAnchor="end"
                                height={80}
                            />
                            <YAxis stroke="#9CA3AF" fontSize={12} />
                            <Tooltip 
                                contentStyle={{ 
                                    backgroundColor: '#1F2937', 
                                    border: '1px solid #374151',
                                    borderRadius: '8px',
                                    color: '#F3F4F6'
                                }}
                            />
                            <Legend />
                            <Bar dataKey="value" fill="#0FEDBE" radius={[8, 8, 0, 0]} />
                        </BarChart>
                    )}
                    
                    {chartType === 'line' && (
                        <LineChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis 
                                dataKey="name" 
                                stroke="#9CA3AF"
                                fontSize={12}
                                angle={-45}
                                textAnchor="end"
                                height={80}
                            />
                            <YAxis stroke="#9CA3AF" fontSize={12} />
                            <Tooltip 
                                contentStyle={{ 
                                    backgroundColor: '#1F2937', 
                                    border: '1px solid #374151',
                                    borderRadius: '8px',
                                    color: '#F3F4F6'
                                }}
                            />
                            <Legend />
                            <Line 
                                type="monotone" 
                                dataKey="value" 
                                stroke="#0FEDBE" 
                                strokeWidth={2}
                                dot={{ fill: '#0FEDBE', r: 4 }}
                                activeDot={{ r: 6 }}
                            />
                        </LineChart>
                    )}
                    
                    {chartType === 'pie' && (
                        <PieChart>
                            <Pie
                                data={chartData}
                                cx="50%"
                                cy="50%"
                                labelLine={false}
                                label={(props) => {
                                    const { name, value, percent } = props as unknown as { name: string; value: number; percent: number };
                                    return `${name}: ${(value ?? 0).toFixed(1)} (${((percent ?? 0) * 100).toFixed(0)}%)`;
                                }}
                                outerRadius={80}
                                fill="#8884d8"
                                dataKey="value"
                            >
                                {chartData.map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                ))}
                            </Pie>
                            <Tooltip 
                                contentStyle={{ 
                                    backgroundColor: '#1F2937', 
                                    border: '1px solid #374151',
                                    borderRadius: '8px',
                                    color: '#F3F4F6'
                                }}
                            />
                            <Legend />
                        </PieChart>
                    )}
                </ResponsiveContainer>
            </div>
        </Card>
    );
}

