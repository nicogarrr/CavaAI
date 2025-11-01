'use client';

import { useState, useRef, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { cn } from '@/lib/utils';

// Lazy load del widget solo cuando sea necesario
const TradingViewWidget = dynamic(
    () => import('@/components/TradingViewWidget'),
    { 
        ssr: false,
        loading: () => (
            <div className="w-full bg-gray-800 rounded-lg border border-gray-700 animate-pulse" style={{ height: 600 }}>
                <div className="h-full flex items-center justify-center">
                    <div className="text-gray-400">Cargando gráfico...</div>
                </div>
            </div>
        )
    }
);

interface LazyTradingViewWidgetProps {
    title?: string;
    scriptUrl: string;
    config: Record<string, unknown>;
    height?: number;
    className?: string;
    priority?: boolean; // Si es true, carga inmediatamente
}

const LazyTradingViewWidget = ({ 
    title, 
    scriptUrl, 
    config, 
    height = 600, 
    className,
    priority = false 
}: LazyTradingViewWidgetProps) => {
    const [isVisible, setIsVisible] = useState(priority);
    const containerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (priority || isVisible) return;

        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        setIsVisible(true);
                        observer.disconnect();
                    }
                });
            },
            {
                rootMargin: '200px', // Cargar 200px antes de que sea visible
                threshold: 0.1,
            }
        );

        if (containerRef.current) {
            observer.observe(containerRef.current);
        }

        return () => {
            observer.disconnect();
        };
    }, [priority, isVisible]);

    return (
        <div ref={containerRef} className={cn('w-full', className)}>
            {title && <h3 className="font-semibold text-2xl text-gray-100 mb-5">{title}</h3>}
            {isVisible ? (
                <TradingViewWidget
                    title={undefined}
                    scriptUrl={scriptUrl}
                    config={config}
                    height={height}
                    className={className}
                />
            ) : (
                <div className="w-full bg-gray-800 rounded-lg border border-gray-700" style={{ height }}>
                    <div className="h-full flex items-center justify-center">
                        <div className="text-gray-400">Scroll para cargar gráfico...</div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default LazyTradingViewWidget;

