'use client';

import { useState, useMemo, ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface PaginatedContentProps {
    content: string;
    itemsPerPage?: number;
    children: (content: string) => ReactNode;
}

export default function PaginatedContent({ content, itemsPerPage = 3000, children }: PaginatedContentProps) {
    const [currentPage, setCurrentPage] = useState(1);

    // Dividir el contenido en chunks basado en longitud de caracteres
    const pages = useMemo(() => {
        if (!content) return [];
        
        // Asegurar que content es un string
        if (typeof content !== 'string') {
            console.error('PaginatedContent: content is not a string', typeof content, content);
            const stringContent = String(content);
            return [stringContent];
        }
        
        const chunks: string[] = [];
        let currentIndex = 0;
        
        while (currentIndex < content.length) {
            const chunk = content.slice(currentIndex, currentIndex + itemsPerPage);
            chunks.push(chunk);
            currentIndex += itemsPerPage;
        }
        
        return chunks;
    }, [content, itemsPerPage]);

    const totalPages = pages.length;
    const currentContent = pages[currentPage - 1] || '';

    if (totalPages <= 1) {
        return <>{children(content)}</>;
    }

    const goToPrevious = () => {
        if (currentPage > 1) {
            setCurrentPage(currentPage - 1);
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    };

    const goToNext = () => {
        if (currentPage < totalPages) {
            setCurrentPage(currentPage + 1);
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    };

    return (
        <div className="space-y-4">
            <div>{children(currentContent)}</div>
            
            <div className="flex items-center justify-between pt-4 border-t border-gray-700">
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
        </div>
    );
}

