'use client';

import { useState, useEffect } from 'react';
import { generateCombinedAnalysis } from '@/lib/actions/ai.actions';
import { getStockFinancialData } from '@/lib/actions/finnhub.actions';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Loader2, Download, FileText } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import PaginatedContent from './PaginatedContent';
import { Skeleton } from '@/components/ui/skeleton';

interface AnalysisGeneratorProps {
    symbol: string;
    companyName: string;
    currentPrice: number;
    onAnalysisGenerated?: (analysis: string | null, loading: boolean) => void;
    isLoading?: boolean;
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
    const [analysis, setAnalysis] = useState<string | null>(null);
    const [isMounted, setIsMounted] = useState(false);

    useEffect(() => {
        setIsMounted(true);
    }, []);

    const handleGenerateAnalysis = async () => {
        setIsLoading(true);
        setError(null);
        setAnalysis(null);

        try {
            const financialData = await getStockFinancialData(symbol);

            if (!financialData) {
                setError('No se pudieron obtener los datos financieros para este símbolo.');
                setIsLoading(false);
                onAnalysisGenerated?.(null, false);
                return;
            }

            const result = await generateCombinedAnalysis({
                symbol,
                companyName,
                financialData,
                currentPrice,
            });

            setAnalysis(result);
            onAnalysisGenerated?.(result, false);
        } catch (err) {
            console.error('Error generating combined analysis:', err);
            setError('Error al generar el análisis completo. Por favor, intenta de nuevo.');
            onAnalysisGenerated?.(null, false);
        } finally {
            setIsLoading(false);
        }
    };

    const handleDownloadPDF = () => {
        if (!analysis) return;

        // Crear un nuevo documento HTML para el PDF
        const printWindow = window.open('', '_blank');
        if (!printWindow) return;

        const htmlContent = `
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Análisis Completo - ${companyName} (${symbol})</title>
    <style>
        @media print {
            @page {
                size: A4;
                margin: 2cm;
            }
            body {
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }
        }
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: white;
            padding: 40px;
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            font-size: 2.5em;
            font-weight: bold;
            margin-bottom: 10px;
            color: #1a1a1a;
            border-bottom: 3px solid #0FEDBE;
            padding-bottom: 10px;
        }
        h2 {
            font-size: 2em;
            font-weight: bold;
            margin-top: 30px;
            margin-bottom: 15px;
            color: #2a2a2a;
            border-bottom: 2px solid #0FEDBE;
            padding-bottom: 8px;
        }
        h3 {
            font-size: 1.5em;
            font-weight: 600;
            margin-top: 25px;
            margin-bottom: 12px;
            color: #3a3a3a;
        }
        h4 {
            font-size: 1.25em;
            font-weight: 600;
            margin-top: 20px;
            margin-bottom: 10px;
            color: #4a4a4a;
        }
        p {
            margin-bottom: 15px;
            line-height: 1.8;
            color: #333;
        }
        ul, ol {
            margin-bottom: 15px;
            margin-left: 30px;
        }
        li {
            margin-bottom: 8px;
            line-height: 1.7;
        }
        strong {
            font-weight: 600;
            color: #1a1a1a;
        }
        code {
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            page-break-inside: avoid;
        }
        thead {
            background: #f8f9fa;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }
        th {
            font-weight: 600;
            background: #e9ecef;
        }
        blockquote {
            border-left: 4px solid #0FEDBE;
            padding-left: 20px;
            margin: 20px 0;
            font-style: italic;
            color: #555;
        }
        hr {
            border: none;
            border-top: 1px solid #ddd;
            margin: 30px 0;
        }
        .header {
            text-align: center;
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 2px solid #0FEDBE;
        }
        .company-name {
            font-size: 1.8em;
            font-weight: bold;
            color: #0FEDBE;
        }
        .symbol {
            font-size: 1.2em;
            color: #666;
        }
        .date {
            color: #888;
            font-size: 0.9em;
            margin-top: 10px;
        }
        @media print {
            .no-print {
                display: none;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="company-name">${companyName}</div>
        <div class="symbol">${symbol}</div>
        <div class="date">Análisis generado: ${new Date().toLocaleDateString('es-ES', { 
            year: 'numeric', 
            month: 'long', 
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        })}</div>
    </div>
    ${analysis.replace(/\n/g, '\n    ')}
</body>
</html>
        `;

        printWindow.document.write(htmlContent);
        printWindow.document.close();
        
        // Esperar a que se cargue el contenido antes de imprimir
        setTimeout(() => {
            printWindow.print();
            // Cerrar la ventana después de imprimir (opcional)
            // setTimeout(() => printWindow.close(), 1000);
        }, 500);
    };

    const isLoadingState = isLoading || externalLoading;
    const showContent = analysis && !isLoadingState && isMounted;

    return (
        <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-6">
                <div className="flex-1">
                    <h2 className="text-2xl font-bold text-gray-100">Análisis Completo de Inversión</h2>
                    <p className="text-sm text-gray-400 mt-2">
                        Análisis exhaustivo integrado: DCF Valuation & Investment Thesis para {companyName} ({symbol})
                    </p>
                </div>
                <div className="flex gap-2">
                    {showContent && (
                        <Button
                            onClick={handleDownloadPDF}
                            variant="outline"
                            size="lg"
                            className="w-full md:w-auto"
                        >
                            <Download className="mr-2 h-4 w-4" />
                            Descargar PDF
                        </Button>
                    )}
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
                            <>
                                <FileText className="mr-2 h-4 w-4" />
                                Generar Análisis Completo
                            </>
                        )}
                    </Button>
                </div>
            </div>

            {error && (
                <div className="mb-6 p-4 bg-destructive/10 border border-destructive/20 rounded-lg">
                    <p className="text-sm text-destructive">{error}</p>
                </div>
            )}

            {/* Mostrar contenido según el estado */}
            {isLoadingState && isMounted && (
                <div className="mt-6 p-6 bg-gray-900/50 rounded-lg border border-gray-700/50">
                    <div className="space-y-4">
                        <Skeleton className="h-8 w-full" />
                        <Skeleton className="h-4 w-3/4" />
                        <Skeleton className="h-4 w-5/6" />
                        <Skeleton className="h-64 w-full" />
                        <Skeleton className="h-32 w-full" />
                        <Skeleton className="h-96 w-full" />
                    </div>
                </div>
            )}

            {!showContent && !isLoadingState && (
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
            )}

            {showContent && (
                <div className="mt-6 border-t border-gray-700 pt-6">
                    <div className="prose prose-invert max-w-none text-foreground">
                        <PaginatedContent content={analysis} itemsPerPage={3000}>
                            {(content) => (
                                <ReactMarkdown
                                    remarkPlugins={[remarkGfm]}
                                    components={{
                                    h1: ({ ...props }) => (
                                        <h1 className="text-3xl font-bold mt-8 mb-4 text-foreground border-b border-border pb-2" {...props} />
                                    ),
                                    h2: ({ ...props }) => (
                                        <h2 className="text-2xl font-bold mt-6 mb-3 text-foreground border-b border-border pb-2" {...props} />
                                    ),
                                    h3: ({ ...props }) => (
                                        <h3 className="text-xl font-semibold mt-4 mb-2 text-foreground" {...props} />
                                    ),
                                    h4: ({ ...props }) => (
                                        <h4 className="text-lg font-semibold mt-3 mb-2 text-foreground" {...props} />
                                    ),
                                    p: ({ ...props }) => (
                                        <p className="mb-4 leading-7 text-foreground/90" {...props} />
                                    ),
                                    ul: ({ ...props }) => (
                                        <ul className="list-disc list-inside mb-4 space-y-2 text-foreground/90 ml-4" {...props} />
                                    ),
                                    ol: ({ ...props }) => (
                                        <ol className="list-decimal list-inside mb-4 space-y-2 text-foreground/90 ml-4" {...props} />
                                    ),
                                    li: ({ ...props }) => (
                                        <li className="ml-4 text-foreground/90 leading-relaxed" {...props} />
                                    ),
                                    strong: ({ ...props }) => (
                                        <strong className="font-semibold text-foreground" {...props} />
                                    ),
                                    code: ({ ...props }) => (
                                        <code className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono text-foreground" {...props} />
                                    ),
                                    table: ({ ...props }) => (
                                        <div className="overflow-x-auto my-6 rounded-lg border border-gray-700 bg-gray-900/50">
                                            <table className="min-w-full border-collapse" {...props} />
                                        </div>
                                    ),
                                    thead: ({ ...props }) => (
                                        <thead className="bg-gray-800" {...props} />
                                    ),
                                    tbody: ({ ...props }) => (
                                        <tbody {...props} />
                                    ),
                                    tr: ({ ...props }) => (
                                        <tr className="border-b border-gray-700 hover:bg-gray-800/50 transition-colors" {...props} />
                                    ),
                                    th: ({ ...props }) => (
                                        <th className="border-r border-gray-700 px-4 py-3 bg-gray-800 font-semibold text-left text-gray-100 first:border-l-0 last:border-r-0" {...props} />
                                    ),
                                    td: ({ ...props }) => (
                                        <td className="border-r border-gray-700 px-4 py-3 text-gray-300 first:border-l-0 last:border-r-0" {...props} />
                                    ),
                                    blockquote: ({ ...props }) => (
                                        <blockquote className="border-l-4 border-primary pl-4 italic my-4 text-foreground/80" {...props} />
                                    ),
                                        }}
                                    >
                                        {content}
                                    </ReactMarkdown>
                                )}
                            </PaginatedContent>
                        </div>
                    </div>
            )}
        </Card>
    );
}
