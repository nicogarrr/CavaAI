'use client';

import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import PaginatedContent from './PaginatedContent';

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

    if (!analysis) {
        return null;
    }

    return (
        <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50">
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
                </Card>
    );
}

