"use client"

import { useEffect, useState, useCallback, useMemo, useRef } from "react"
import { useRouter } from "next/navigation"
import { CommandDialog, CommandEmpty, CommandInput, CommandList } from "@/components/ui/command"
import { Loader2, TrendingUp, Search } from "lucide-react";
import { searchStocks } from "@/lib/actions/finnhub.actions";
import { showErrorToast } from "@/lib/toast";
import { isNextRedirectError } from "@/lib/types/errors";

export default function SearchCommand({ renderAs = 'button', label = 'Añadir acción', initialStocks }: SearchCommandProps) {
    const router = useRouter();
    const [open, setOpen] = useState(false)
    const [searchTerm, setSearchTerm] = useState("")
    const [loading, setLoading] = useState(false)
    const [searchError, setSearchError] = useState(false)
    const [stocks, setStocks] = useState<StockWithWatchlistStatus[]>(initialStocks);
    const [mounted, setMounted] = useState(false);
    const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const abortControllerRef = useRef<AbortController | null>(null);

    const isSearchMode = !!searchTerm.trim();

    const displayStocks = useMemo(() => {
        return isSearchMode ? stocks : (stocks?.slice(0, 10) || []);
    }, [isSearchMode, stocks]);

    useEffect(() => {
        setMounted(true);
    }, []);

    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
                e.preventDefault()
                setOpen(v => !v)
            }
        }
        window.addEventListener("keydown", onKeyDown)
        return () => window.removeEventListener("keydown", onKeyDown)
    }, [])

    const handleSearch = useCallback(async (query: string) => {
        // Cancelar búsqueda anterior si existe
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }

        if (!query.trim()) {
            setStocks(initialStocks);
            setSearchError(false);
            setLoading(false);
            return;
        }

        // Crear nuevo AbortController para esta búsqueda
        const controller = new AbortController();
        abortControllerRef.current = controller;

        setLoading(true);
        setSearchError(false);
        try {
            const results = await searchStocks(query.trim());

            // Solo actualizar si el request no fue cancelado
            if (!controller.signal.aborted) {
                setStocks(results || []);
            }
        } catch (error: unknown) {
            // Ignorar errores de cancelación; ante un fallo real, mostrar el
            // error honesto SIN vaciar los resultados anteriores. El redirect
            // de Next se re-lanza (forma parte de la navegación).
            const aborted = error instanceof Error && error.name === 'AbortError';
            if (!aborted && !controller.signal.aborted) {
                if (isNextRedirectError(error)) throw error;
                setSearchError(true);
                showErrorToast(error, { onRetry: () => handleSearch(query.trim()) });
            }
        } finally {
            if (!controller.signal.aborted) {
                setLoading(false);
            }
        }
    }, [initialStocks]);

    // Debounce efectivo
    useEffect(() => {
        // Limpiar timeout anterior
        if (searchTimeoutRef.current) {
            clearTimeout(searchTimeoutRef.current);
        }

        // Cancelar request anterior
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }

        const trimmedQuery = searchTerm.trim();

        if (!trimmedQuery) {
            setStocks(initialStocks);
            setSearchError(false);
            setLoading(false);
            return;
        }

        // Establecer nuevo timeout
        searchTimeoutRef.current = setTimeout(() => {
            handleSearch(trimmedQuery);
        }, 300);

        // Cleanup
        return () => {
            if (searchTimeoutRef.current) {
                clearTimeout(searchTimeoutRef.current);
            }
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
        };
    }, [searchTerm, handleSearch, initialStocks]);

    // Limpiar cuando se cierra el diálogo
    useEffect(() => {
        if (!open) {
            setSearchTerm("");
            setStocks(initialStocks);
            setSearchError(false);
            if (searchTimeoutRef.current) {
                clearTimeout(searchTimeoutRef.current);
            }
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
        }
    }, [open, initialStocks]);

    const handleSelectStock = useCallback((symbol: string) => {
        // Close dialog and navigate immediately
        setOpen(false);
        setSearchTerm("");
        setStocks(initialStocks);
        // Use router.push for faster navigation
        router.push(`/research/${symbol.toUpperCase()}`);
    }, [initialStocks, router]);

    // Prefetch de la ficha al pasar el cursor o enfocar: navegación instantánea
    const handlePrefetchStock = useCallback((symbol: string) => {
        router.prefetch(`/research/${symbol.toUpperCase()}`);
    }, [router]);

    // Evitar hydration mismatch: el fallback pre-hidrato debe ser
    // visualmente IDENTICO al boton hidratado (input sutil), no una pildora
    // primaria con el label crudo. Sin onClick hasta montar.
    if (!mounted) {
        return (
            <button
                type="button"
                tabIndex={-1}
                aria-hidden="true"
                className="flex min-h-[44px] items-center gap-2 w-full px-4 py-2.5 text-sm text-gray-400 bg-gray-800/60 border border-gray-700 rounded-lg backdrop-blur-sm"
            >
                <Search className="w-4 h-4 text-gray-500" />
                <span className="flex-1 text-left">Buscar acciones...</span>
                <kbd className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 text-xs text-gray-500 bg-gray-900/50 border border-gray-600 rounded">
                    Ctrl+K
                </kbd>
            </button>
        );
    }

    return (
        <>
            {renderAs === 'text' ? (
                <button
                    type="button"
                    onClick={() => setOpen(true)}
                    className="search-text"
                    aria-label="Abrir buscador"
                >
                    {label}
                </button>
            ) : (
                <button
                    onClick={() => setOpen(true)}
                    className="flex min-h-[44px] items-center gap-2 w-full px-4 py-2.5 text-sm text-gray-400 bg-gray-800/60 hover:bg-gray-700/60 border border-gray-700 rounded-lg transition-all duration-200 backdrop-blur-sm"
                    aria-label="Abrir buscador"
                >
                    <Search className="w-4 h-4 text-gray-500" />
                    <span className="flex-1 text-left">Buscar acciones...</span>
                    <kbd className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 text-xs text-gray-500 bg-gray-900/50 border border-gray-600 rounded">
                        Ctrl+K
                    </kbd>
                </button>
            )}
            <CommandDialog open={open} onOpenChange={setOpen} className="search-dialog">
                <div className="search-field">
                    <CommandInput value={searchTerm} onValueChange={setSearchTerm} placeholder="Buscar acciones..." className="search-input" />
                    {loading && <Loader2 className="search-loader" />}
                </div>
                <CommandList className="search-list">
                    {loading ? (
                        <CommandEmpty className="search-list-empty">Cargando acciones...</CommandEmpty>
                    ) : searchError ? (
                        <div role="alert" className="search-list-indicator">
                            No se pudo completar la búsqueda. Inténtalo de nuevo.
                        </div>
                    ) : displayStocks?.length === 0 ? (
                        <div className="search-list-indicator">
                            {isSearchMode ? 'Sin resultados' : 'No hay acciones disponibles'}
                        </div>
                    ) : (
                        <ul>
                            <div className="search-count">
                                {isSearchMode ? 'Resultados de búsqueda' : 'Acciones populares'}
                                {` `}({displayStocks?.length || 0})
                            </div>
                            {displayStocks?.map((stock, index) => (
                                <li key={`${stock.symbol}-${index}`} className="search-item">
                                    <button
                                        onClick={() => handleSelectStock(stock.symbol)}
                                        onMouseEnter={() => handlePrefetchStock(stock.symbol)}
                                        onFocus={() => handlePrefetchStock(stock.symbol)}
                                        title={`${stock.name} (${stock.symbol})`}
                                        className="search-item-link w-full text-left"
                                    >
                                        <TrendingUp className="h-4 w-4 text-gray-500" />
                                        <div className="flex-1 min-w-0">
                                            <div className="search-item-name truncate" title={stock.name}>
                                                {stock.name}
                                            </div>
                                            <div className="text-sm text-gray-500">
                                                {stock.symbol} | {stock.exchange} | {stock.type}
                                            </div>
                                        </div>
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                </CommandList>
            </CommandDialog>
        </>
    )
}
