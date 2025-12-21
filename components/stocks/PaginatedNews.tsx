'use client';

import { useState } from 'react';
import Image from 'next/image';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ExternalLink, Clock, ChevronLeft, ChevronRight } from 'lucide-react';

interface NewsArticle {
    id: string;
    headline: string;
    summary: string;
    url: string;
    source?: string;
    datetime?: number;
    image?: string;
    related?: string;
}

interface PaginatedNewsProps {
    articles: NewsArticle[];
    itemsPerPage?: number;
}

export default function PaginatedNews({ articles, itemsPerPage = 3 }: PaginatedNewsProps) {
    const [currentPage, setCurrentPage] = useState(1);

    if (articles.length === 0) {
        return (
            <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50">
                <h2 className="text-xl font-semibold mb-4 text-gray-200">Noticias Recientes</h2>
                <div className="flex items-center justify-center h-48 text-gray-500">
                    <p>No hay noticias disponibles en este momento.</p>
                </div>
            </Card>
        );
    }

    const totalPages = Math.ceil(articles.length / itemsPerPage);
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    const currentArticles = articles.slice(startIndex, endIndex);

    const goToPrevious = () => {
        if (currentPage > 1) {
            setCurrentPage(currentPage - 1);
            // Mantener posición de scroll al cambiar de página
        }
    };

    const goToNext = () => {
        if (currentPage < totalPages) {
            setCurrentPage(currentPage + 1);
            // Mantener posición de scroll al cambiar de página
        }
    };

    return (
        <Card className="p-6 rounded-lg border border-gray-700 bg-gray-800/50">
            <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold text-gray-200">Noticias Recientes</h2>
                <span className="text-sm text-gray-400">{articles.length} artículos</span>
            </div>

            <div className="space-y-4">
                {currentArticles.map((article, index) => (
                    <a
                        key={article.id || `article-${startIndex + index}`}
                        href={article.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block p-4 bg-gray-900/50 hover:bg-gray-900 rounded-lg border border-gray-700/50 transition-all duration-200 group"
                    >
                        <div className="flex gap-4">
                            {article.image && (
                                <div className="flex-shrink-0 w-32 h-24 relative rounded-lg overflow-hidden">
                                    <Image
                                        src={article.image}
                                        alt={article.headline}
                                        fill
                                        className="object-cover"
                                        unoptimized
                                    />
                                </div>
                            )}
                            <div className="flex-1 min-w-0">
                                <div className="flex items-start justify-between gap-2 mb-2">
                                    <h3 className="text-gray-100 font-semibold line-clamp-2 group-hover:text-teal-400 transition-colors flex-1">
                                        {article.headline}
                                    </h3>
                                    <ExternalLink className="h-4 w-4 text-gray-500 flex-shrink-0 mt-1 opacity-0 group-hover:opacity-100 transition-opacity" />
                                </div>
                                <p className="text-gray-400 text-sm mb-3 line-clamp-2">
                                    {article.summary}
                                </p>
                                <div className="flex items-center gap-4 text-xs text-gray-500">
                                    {article.source && (
                                        <span className="font-medium text-teal-400">
                                            {article.source}
                                        </span>
                                    )}
                                    {article.datetime && (
                                        <div className="flex items-center gap-1">
                                            <Clock className="h-3 w-3" />
                                            <span>
                                                {new Date(article.datetime * 1000).toLocaleDateString('es-ES', {
                                                    day: 'numeric',
                                                    month: 'short',
                                                    year: 'numeric',
                                                    hour: '2-digit',
                                                    minute: '2-digit',
                                                })}
                                            </span>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </a>
                ))}
            </div>

            {totalPages > 1 && (
                <div className="flex items-center justify-between pt-4 mt-6 border-t border-gray-700">
                    <div className="flex items-center gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={goToPrevious}
                            disabled={currentPage === 1}
                            className="gap-2"
                        >
                            <ChevronLeft className="h-4 w-4" />
                            Anterior
                        </Button>

                        <span className="text-sm text-gray-400 px-4">
                            Página {currentPage} de {totalPages}
                        </span>

                        <Button
                            variant="outline"
                            size="sm"
                            onClick={goToNext}
                            disabled={currentPage === totalPages}
                            className="gap-2"
                        >
                            Siguiente
                            <ChevronRight className="h-4 w-4" />
                        </Button>
                    </div>
                </div>
            )}
        </Card>
    );
}

