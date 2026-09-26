"use client"

import { useEffect, useState, useCallback, useMemo, useRef } from "react"
import { useRouter } from "next/navigation"
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
import { CornerDownLeft, Loader2, Search, TrendingUp } from "lucide-react";
import { searchStocks } from "@/lib/actions/finnhub.actions";
import { showErrorToast } from "@/lib/toast";
import { isNextRedirectError } from "@/lib/types/errors";
import { flattenNavItems, NAV_SECTIONS } from "@/lib/constants";

export default function SearchCommand({ renderAs = 'button', label = 'Añadir acción', initialStocks }: SearchCommandProps) {
    const router = useRouter()
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

    // Atajos: Ctrl/Cmd+K y "/". "/" solo cuando el foco no esta en un campo de
    // texto, para no secuestrar la escritura.
    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
                e.preventDefault()
                setOpen(v => !v)
                return
            }
            if (e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey) {
                const target = e.target as HTMLElement | null
                const tag = target?.tagName
                if (tag === 'INPUT' || tag === 'TEXTAREA' || target?.isContentEditable) return
                e.preventDefault()
                setOpen(true)
            }
        }
        window.addEventListener("keydown", onKeyDown)
        return () => window.removeEventListener("keydown", onKeyDown)
    }, [])

    useEffect(() => {
        setMounted(true);
    }, []);

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

    const go = useCallback((href: string) => {
        setOpen(false);
        setSearchTerm("");
        router.push(href);
    }, [router]);

    const handleSelectStock = useCallback((symbol: string) => {
        go(`/research/${symbol.toUpperCase()}`);
    }, [go]);

    // Prefetch de la ficha al pasar el cursor o enfocar: navegación instantánea
    const handlePrefetchStock = useCallback((symbol: string) => {
        router.prefetch(`/research/${symbol.toUpperCase()}`);
    }, [router]);

    // Evitar hydration mismatch: el fallback pre-hidratado debe ser
    // visualmente IDENTICO al boton hidratado (input sutil), no una pildora
    // primaria con el label crudo. Sin onClick hasta montar.
    if (!mounted) {
        return (
            <button
                type="button"
                tabIndex={-1}
                aria-hidden="true"
                className="flex min-h-11 w-full items-center gap-2 rounded-lg border border-gray-700 bg-gray-800/60 px-4 py-2.5 text-sm text-gray-400 backdrop-blur-sm"
            >
                <Search aria-hidden="true" className="h-4 w-4 text-gray-500" />
                <span className="flex-1 text-left">Buscar acciones...</span>
                <kbd className="hidden items-center gap-1 rounded border border-gray-600 bg-gray-900/50 px-2 py-0.5 text-xs text-gray-500 sm:inline-flex">
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
            ) : renderAs === 'icon' ? (
                <button
                    type="button"
                    onClick={() => setOpen(true)}
                    aria-label="Abrir buscador"
                    className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg p-2 text-gray-300 transition-colors hover:bg-gray-700/50 hover:text-white"
                >
                    <Search aria-hidden="true" className="h-5 w-5" />
                </button>
            ) : (
                <button
                    type="button"
                    onClick={() => setOpen(true)}
                    className="flex min-h-11 w-full items-center gap-2 rounded-lg border border-gray-700 bg-gray-800/60 px-4 py-2.5 text-sm text-gray-400 backdrop-blur-sm transition-all duration-200 hover:bg-gray-700/60"
                    aria-label="Abrir buscador"
                >
                    <Search aria-hidden="true" className="h-4 w-4 text-gray-500" />
                    <span className="flex-1 text-left">Buscar acciones...</span>
                    <kbd className="hidden items-center gap-1 rounded border border-gray-600 bg-gray-900/50 px-2 py-0.5 text-xs text-gray-500 sm:inline-flex">
                        Ctrl+K
                    </kbd>
                </button>
            )}
            <CommandDialog
                open={open}
                onOpenChange={setOpen}
                className="search-dialog"
                title="Buscar acciones"
                description="Busca por símbolo o empresa, o salta a una sección de CavaAI"
            >
                <div className="search-field">
                    <CommandInput
                        value={searchTerm}
                        onValueChange={setSearchTerm}
                        placeholder="Buscar acciones..."
                        aria-label="Buscar acciones o secciones"
                        className="search-input"
                    />
                    {loading && <Loader2 aria-hidden="true" className="search-loader" />}
                </div>
                <CommandList className="search-list">
                    {loading ? (
                        <CommandEmpty className="search-list-empty">Cargando acciones...</CommandEmpty>
                    ) : searchError ? (
                        <div role="alert" className="search-list-indicator">
                            No se pudo completar la búsqueda. Inténtalo de nuevo.
                        </div>
                    ) : (
                        <>
                            {/* Secciones navegables: el buscador deja de ser solo
                                un buscador de tickers y cubre los destinos que no
                                caben en el menu. */}
                            {!isSearchMode && (
                                <>
                                    {NAV_SECTIONS.filter((section) => section.items.length > 1).map((section) => (
                                        <CommandGroup
                                            key={section.title}
                                            heading={section.title}
                                            className="[&_[cmdk-group-heading]]:px-4 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wide [&_[cmdk-group-heading]]:text-gray-500"
                                        >
                                            {flattenNavItems([section]).map((item) => (
                                                <CommandItem
                                                    key={item.href}
                                                    value={`ir ${item.label}`}
                                                    onSelect={() => go(item.href)}
                                                    className="flex min-h-11 items-center gap-2 px-4"
                                                >
                                                    {item.icon && <item.icon aria-hidden="true" className="h-4 w-4 text-gray-500" />}
                                                    <span className="flex-1 truncate">{item.label}</span>
                                                    <CornerDownLeft aria-hidden="true" className="h-3.5 w-3.5 text-gray-600" />
                                                </CommandItem>
                                            ))}
                                        </CommandGroup>
                                    ))}
                                </>
                            )}

                            {displayStocks?.length === 0 ? (
                                <div className="search-list-indicator">
                                    {isSearchMode ? 'Sin resultados' : 'No hay acciones disponibles'}
                                </div>
                            ) : (
                                <ul className="search-results">
                                    <li className="search-count">
                                        {isSearchMode ? 'Resultados de búsqueda' : 'Acciones populares'}
                                        {` `}({displayStocks?.length || 0})
                                    </li>
                                    {displayStocks?.map((stock, index) => (
                                        <li key={`${stock.symbol}-${index}`} className="search-item">
                                            <button
                                                onClick={() => handleSelectStock(stock.symbol)}
                                                onMouseEnter={() => handlePrefetchStock(stock.symbol)}
                                                onFocus={() => handlePrefetchStock(stock.symbol)}
                                                title={`${stock.name} (${stock.symbol})`}
                                                className="search-item-link w-full text-left"
                                            >
                                                <TrendingUp aria-hidden="true" className="h-4 w-4 text-gray-500" />
                                                <div className="min-w-0 flex-1">
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
                        </>
                    )}
                </CommandList>
            </CommandDialog>
        </>
    )
}
