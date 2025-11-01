'use client';

import { useState } from 'react';
import { generateCombinedAnalysis } from '@/lib/actions/ai.actions';
import { getStockFinancialData } from '@/lib/actions/finnhub.actions';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Loader2 } from 'lucide-react';

interface AnalysisGeneratorProps {
    symbol: string;
    companyName: string;
    currentPrice: number;
    onAnalysisGenerated: (analysis: string | null, loading: boolean) => void;
    isLoading: boolean;
}

export default function AnalysisGenerator({ 
    symbol, 
    companyName, 
    currentPrice, 
    onAnalysisGenerated,
    isLoading: externalLoading
}: AnalysisGeneratorProps) {
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleGenerateAnalysis = async () => {
        setIsLoading(true);
        setError(null);
        onAnalysisGenerated(null, true); // Limpiar análisis anterior y establecer loading

        try {
            const financialData = await getStockFinancialData(symbol);

            if (!financialData) {
                setError('No se pudieron obtener los datos financieros para este símbolo.');
                setIsLoading(false);
                onAnalysisGenerated(null, false);
                return;
            }

            const result = await generateCombinedAnalysis({
                symbol,
                companyName,
                financialData,
                currentPrice,
            });

            onAnalysisGenerated(result, false);
        } catch (err) {
            console.error('Error generating combined analysis:', err);
            setError('Error al generar el análisis completo. Por favor, intenta de nuevo.');
            onAnalysisGenerated(null, false);
        } finally {
            setIsLoading(false);
        }
    };

    const isLoadingState = isLoading || externalLoading;

    return (
        <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                <div className="flex-1">
                    <h2 className="text-2xl font-bold text-gray-100">Análisis Completo de Inversión</h2>
                    <p className="text-sm text-gray-400 mt-2">
                        Análisis exhaustivo integrado: DCF Valuation & Investment Thesis para {companyName} ({symbol})
                    </p>
                </div>
                <Button
                    onClick={handleGenerateAnalysis}
                    disabled={isLoadingState}
                    variant="default"
                    size="lg"
                    className="w-full md:w-auto"
                >
                    {isLoadingState ? (
                        <>
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            Generando...
                        </>
                    ) : (
                        'Generar Análisis Completo'
                    )}
                </Button>
            </div>

            {error && (
                <div className="mt-4 p-4 bg-destructive/10 border border-destructive/20 rounded-lg">
                    <p className="text-sm text-destructive">{error}</p>
                </div>
            )}

            <div className="mt-6 p-6 bg-gray-900/50 rounded-lg border border-gray-700/50">
                <p className="text-sm text-gray-400 mb-4">
                    El análisis incluirá:
                </p>
                <ul className="text-sm text-gray-300 space-y-2 columns-1 md:columns-2 gap-4">
                    <li>• DCF Valuation completo con proyecciones financieras</li>
                    <li>• Investment Thesis con análisis de moat y competencia</li>
                    <li>• Visualizaciones descritas (gráficos, tablas)</li>
                    <li>• Comparativas competitivas</li>
                    <li>• Moat Resilience Index (MRI)</li>
                    <li>• Market-Implied Expectations (Reverse DCF)</li>
                    <li>• Escenarios (Bear, Base, Bull) con probabilidades</li>
                    <li>• Margen de seguridad y veredicto final</li>
                </ul>
            </div>
        </Card>
    );
}

