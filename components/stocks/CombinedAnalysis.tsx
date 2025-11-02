'use client';

import { useState, useMemo, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import PaginatedContent from './PaginatedContent';
import TableVisualization from './TableVisualization';
import { fixAllMarkdownTables, findAllTables } from '@/lib/utils/tableFormatter';

interface CombinedAnalysisProps {
    analysis: string | null;
    isLoading: boolean;
}

export default function CombinedAnalysis({ analysis, isLoading }: CombinedAnalysisProps) {
    const [isMounted, setIsMounted] = useState(false);
    
    // Asegurar que solo se renderiza en el cliente para evitar problemas de hidratación
    useEffect(() => {
        setIsMounted(true);
    }, []);
    
    // Corregir tablas mal formateadas antes de renderizar
    const correctedAnalysis = useMemo(() => {
        if (!analysis) return null;
        
        // Asegurar que analysis es un string
        if (typeof analysis !== 'string') {
            console.error('CombinedAnalysis: analysis is not a string', typeof analysis, analysis);
            return String(analysis);
        }
        
        try {
            return fixAllMarkdownTables(analysis);
        } catch (error) {
            console.error('Error fixing markdown tables:', error);
            return analysis; // Retornar análisis original si hay error
        }
    }, [analysis]);
    
    // Extraer todas las tablas para visualizaciones
    const tables = useMemo(() => {
        if (!correctedAnalysis) return [];
        try {
            return findAllTables(correctedAnalysis);
        } catch (error) {
            console.error('Error finding tables:', error);
            return [];
        }
    }, [correctedAnalysis]);
    
    // Mostrar skeleton mientras se monta o está cargando
    if (!isMounted || isLoading) {
        return (
            <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50">
                <div className="space-y-4">
                    <Skeleton className="h-8 w-full" />
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-4 w-5/6" />
                    <Skeleton className="h-64 w-full" />
                    <Skeleton className="h-32 w-full" />
                    <Skeleton className="h-96 w-full" />
                </div>
            </Card>
        );
    }

    if (!analysis || !correctedAnalysis) {
        return null;
    }

    return (
        <div className="space-y-6">
            <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50">
                <div className="prose prose-invert max-w-none text-foreground">
                    <PaginatedContent content={correctedAnalysis} itemsPerPage={3000}>
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
                </Card>
            
            {/* Visualizaciones de tablas */}
            {tables.length > 0 && (
                <div className="space-y-6">
                    {tables.map((table, index) => {
                        if (table.headers.length < 2 || table.rows.length === 0) return null;
                        
                        // Determinar tipo de gráfico basado en los headers
                        let chartType: 'bar' | 'line' | 'pie' = 'bar';
                        const headers = table.headers.map(h => h.toLowerCase());
                        
                        if (headers.some(h => h.includes('año') || h.includes('year') || h.includes('tiempo'))) {
                            chartType = 'line';
                        } else if (table.rows.length <= 10) {
                            chartType = 'bar';
                        }
                        
                        return (
                            <TableVisualization
                                key={index}
                                tableMarkdown={table.raw}
                                title={table.headers[0] || `Tabla ${index + 1}`}
                                chartType={chartType}
                            />
                        );
                    })}
                </div>
            )}
        </div>
    );
}

