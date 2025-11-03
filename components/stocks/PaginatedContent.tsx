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

  // Dividir el contenido de forma inteligente por secciones o párrafos
  const pages = useMemo(() => {
    if (!content) return [];
    
    // Asegurar que content es un string
    if (typeof content !== 'string') {
      console.error('PaginatedContent: content is not a string', typeof content, content);
      const stringContent = String(content);
      return [stringContent];
    }
    
    const chunks: string[] = [];
    const targetChunkSize = itemsPerPage;
    let currentIndex = 0;
    const contentLength = content.length;
    
    // Función para encontrar el próximo punto de corte inteligente
    const findBreakPoint = (startIndex: number, maxLength: number): number => {
      const endIndex = Math.min(startIndex + maxLength, contentLength);
      
      // 1. Intentar encontrar un encabezado de sección (## o ###)
      const sectionHeaderRegex = /^#{2,3}\s+/gm;
      let match;
      let bestBreak = endIndex;
      sectionHeaderRegex.lastIndex = startIndex;
      
      while ((match = sectionHeaderRegex.exec(content)) !== null && match.index < endIndex) {
        // Si el encabezado está dentro del rango y no está demasiado cerca del inicio
        if (match.index > startIndex + targetChunkSize * 0.3 && match.index < endIndex) {
          bestBreak = match.index;
          break; // Usar el primer encabezado encontrado en un buen punto
        }
        // Si está más cerca del final, guardarlo como opción
        if (match.index > startIndex && match.index < endIndex) {
          bestBreak = match.index;
        }
      }
      
      // 2. Si no hay sección cerca del final, buscar un doble salto de línea (párrafo)
      if (bestBreak >= endIndex - 100) {
        const paragraphRegex = /\n\n+/g;
        paragraphRegex.lastIndex = startIndex;
        let paraMatch;
        
        while ((paraMatch = paragraphRegex.exec(content)) !== null && paraMatch.index < endIndex) {
          // Si el párrafo está dentro del rango y en un buen punto
          if (paraMatch.index > startIndex + targetChunkSize * 0.3 && paraMatch.index < endIndex) {
            bestBreak = paraMatch.index + paraMatch[0].length;
            break; // Usar el primer párrafo encontrado en un buen punto
          }
          // Si está más cerca del final, guardarlo como opción
          if (paraMatch.index > startIndex && paraMatch.index < endIndex) {
            bestBreak = paraMatch.index + paraMatch[0].length;
          }
        }
      }
      
      // 3. Si no hay párrafo cerca del final, buscar un salto de línea simple
      if (bestBreak >= endIndex - 50) {
        const lineBreakIndex = content.lastIndexOf('\n', endIndex);
        if (lineBreakIndex > startIndex + targetChunkSize * 0.3) {
          bestBreak = lineBreakIndex + 1;
        }
      }
      
      // 4. Como último recurso, buscar un espacio para no cortar palabras
      if (bestBreak >= endIndex - 20) {
        const spaceIndex = content.lastIndexOf(' ', endIndex);
        if (spaceIndex > startIndex + targetChunkSize * 0.5) {
          bestBreak = spaceIndex + 1;
        }
      }
      
      return Math.max(bestBreak, startIndex + targetChunkSize * 0.5); // Nunca cortar antes del 50%
    };
    
    // Dividir el contenido de forma inteligente
    while (currentIndex < contentLength) {
      const breakPoint = findBreakPoint(currentIndex, targetChunkSize);
      
      // Prevenir bucles infinitos: asegurar progreso mínimo
      if (breakPoint <= currentIndex) {
        // Si no hay progreso, forzar avance
        currentIndex = Math.min(currentIndex + targetChunkSize, contentLength);
        continue;
      }
      
      const chunk = content.slice(currentIndex, breakPoint);
      if (chunk.trim().length > 0) {
        chunks.push(chunk.trim());
      }
      currentIndex = breakPoint;
    }
    
    // Filtrar chunks vacíos
    return chunks.filter(chunk => chunk.length > 0);
  }, [content, itemsPerPage]);

    const totalPages = pages.length;
    const currentContent = pages[currentPage - 1] || '';

    if (totalPages <= 1) {
        return <>{children(content)}</>;
    }

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

