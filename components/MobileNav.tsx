'use client';

import { useEffect, useState } from 'react';
import { Menu, X } from 'lucide-react';
import { CavaAIWordmark } from '@/components/CavaAIWordmark';
import NavItems from '@/components/NavItems';

/**
 * Navegación móvil: botón hamburger (≥44px) que abre un drawer lateral
 * con acceso a TODAS las secciones. En desktop no se renderiza el botón
 * (la navegación completa vive en el header, visible desde `sm`).
 */
export default function MobileNav({ initialStocks }: { initialStocks: StockWithWatchlistStatus[] }) {
    const [open, setOpen] = useState(false);
    void initialStocks;

    // Cerrar con Escape y bloquear el scroll del body mientras está abierto
    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setOpen(false);
        };
        document.addEventListener('keydown', onKey);
        const prev = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        return () => {
            document.removeEventListener('keydown', onKey);
            document.body.style.overflow = prev;
        };
    }, [open ]);

    return (
        <>
            <button
                type="button"
                onClick={() => setOpen(true)}
                aria-label="Abrir menú de navegación"
                aria-expanded={open}
                aria-controls="mobile-nav-drawer"
                className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg p-2 text-gray-300 transition-colors hover:bg-gray-700/50 hover:text-white sm:hidden"
            >
                <Menu className="h-6 w-6" aria-hidden="true" />
            </button>

            {open && (
                <div className="fixed inset-0 z-[60] sm:hidden" role="dialog" aria-modal="true" aria-label="Menú de navegación">
                    <button
                        type="button"
                        aria-label="Cerrar menú de navegación"
                        onClick={() => setOpen(false)}
                        className="absolute inset-0 cursor-default bg-black/60 backdrop-blur-sm"
                    />
                    <aside
                        id="mobile-nav-drawer"
                        className="absolute left-0 top-0 flex h-full max-h-dvh w-[85vw] max-w-xs flex-col border-r border-gray-700/50 bg-gray-900 shadow-2xl"
                    >
                        <div className="flex min-h-[64px] items-center justify-between gap-2 border-b border-gray-700/50 px-4 py-3">
                            <CavaAIWordmark />
                            <button
                                type="button"
                                onClick={() => setOpen(false)}
                                aria-label="Cerrar menú de navegación"
                                className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg p-2 text-gray-300 transition-colors hover:bg-gray-700/50 hover:text-white"
                            >
                                <X className="h-6 w-6" aria-hidden="true" />
                            </button>
                        </div>
                        <nav className="flex-1 overflow-y-auto p-2" aria-label="Navegación principal" onClick={() => setOpen(false)}>
                            <NavItems initialStocks={initialStocks} />
                        </nav>
                        <p className="border-t border-gray-700/50 px-4 py-3 text-xs text-gray-500">
                            Usa el buscador (Ctrl+K) para ir a cualquier acción.
                        </p>
                    </aside>
                </div>
            )}
        </>
    );
}
