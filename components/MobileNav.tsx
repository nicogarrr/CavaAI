'use client';

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
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
    const triggerRef = useRef<HTMLButtonElement>(null);
    const drawerRef = useRef<HTMLDivElement>(null);

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

    // Al abrir: foco al botón de cerrar. Al cerrar: retorno al trigger.
    // (wasOpen evita robar el foco en el montaje inicial)
    const wasOpen = useRef(false);
    useEffect(() => {
        if (open) {
            wasOpen.current = true;
            drawerRef.current
                ?.querySelector<HTMLButtonElement>('button[aria-label="Cerrar menú de navegación"]')
                ?.focus();
        } else if (wasOpen.current) {
            wasOpen.current = false;
            triggerRef.current?.focus();
        }
    }, [open ]);

    // Trampa de foco dentro del drawer mientras está abierto
    const onDrawerKeyDown = (e: React.KeyboardEvent) => {
        if (e.key !== 'Tab' || !drawerRef.current) return;
        const focusables = drawerRef.current.querySelectorAll<HTMLElement>(
            'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );
        if (!focusables.length) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
        }
    };

    return (
        <>
            <button
                type="button"
                ref={triggerRef}
                onClick={() => setOpen(true)}
                aria-label="Abrir menú de navegación"
                aria-expanded={open}
                aria-controls="mobile-nav-drawer"
                className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg p-2 text-gray-300 transition-colors hover:bg-gray-700/50 hover:text-white sm:hidden"
            >
                <Menu className="h-6 w-6" aria-hidden="true" />
            </button>

            {/* Portal a document.body: el header usa backdrop-blur, que convierte
                position:fixed de los descendientes en relativo al header y
                aplastaba el drawer sobre el contenido (capas solapadas). */}
            {open && createPortal(
                <div className="fixed inset-0 z-[60] sm:hidden" role="dialog" aria-modal="true" aria-label="Menú de navegación">
                    <button
                        type="button"
                        aria-label="Cerrar menú de navegación"
                        onClick={() => setOpen(false)}
                        tabIndex={-1}
                        className="absolute inset-0 cursor-default bg-black/60 backdrop-blur-sm"
                    />
                    <aside
                        id="mobile-nav-drawer"
                        ref={drawerRef}
                        onKeyDown={onDrawerKeyDown}
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
                </div>,
                document.body,
            )}
        </>
    );
}
