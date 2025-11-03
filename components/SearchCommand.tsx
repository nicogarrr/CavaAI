"use client"

import { useEffect, useState, useCallback, useMemo, useRef } from "react"
import { CommandDialog, CommandEmpty, CommandInput, CommandList } from "@/components/ui/command"
import {Button} from "@/components/ui/button";
import {Loader2,  TrendingUp, ExternalLink} from "lucide-react";
import Link from "next/link";
import {searchStocks} from "@/lib/actions/finnhub.actions";

export default function SearchCommand({ renderAs = 'button', label = 'Add stock', initialStocks }: SearchCommandProps) {
    const [open, setOpen] = useState(false)
    const [searchTerm, setSearchTerm] = useState("")
    const [loading, setLoading] = useState(false)
    const [stocks, setStocks] = useState<StockWithWatchlistStatus[]>(initialStocks);
    const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const abortControllerRef = useRef<AbortController | null>(null);

    const isSearchMode = !!searchTerm.trim();
    
    const displayStocks = useMemo(() => {
        return isSearchMode ? stocks : (stocks?.slice(0, 10) || []);
    }, [isSearchMode, stocks]);

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
            setLoading(false);
            return;
        }

        // Crear nuevo AbortController para esta búsqueda
        const controller = new AbortController();
        abortControllerRef.current = controller;

        setLoading(true);
        try {
            const results = await searchStocks(query.trim());
            
            // Solo actualizar si el request no fue cancelado
            if (!controller.signal.aborted) {
                setStocks(results || []);
            }
        } catch (error: any) {
            // Ignorar errores de cancelación
            if (error?.name !== 'AbortError' && !controller.signal.aborted) {
                setStocks([]);
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
            if (searchTimeoutRef.current) {
                clearTimeout(searchTimeoutRef.current);
            }
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
        }
    }, [open, initialStocks]);

    const handleSelectStock = useCallback(() => {
        // Close dialog immediately for better UX
        setOpen(false);
        setSearchTerm("");
        setStocks(initialStocks);
    }, [initialStocks]);

    return (
        <>
            {renderAs === 'text' ? (
                <button
                    type="button"
                    onClick={() => setOpen(true)}
                    className="search-text"
                >
                    {label}
                </button>
            ): (
                <Button onClick={() => setOpen(true)} className="search-btn">
                    {label}
                </Button>
            )}
            <CommandDialog open={open} onOpenChange={setOpen} className="search-dialog">
                <div className="search-field">
                    <CommandInput value={searchTerm} onValueChange={setSearchTerm} placeholder="Search stocks..." className="search-input" />
                    {loading && <Loader2 className="search-loader" />}
                </div>
                <CommandList className="search-list">
                    {loading ? (
                        <CommandEmpty className="search-list-empty">Loading stocks...</CommandEmpty>
                    ) : displayStocks?.length === 0 ? (
                        <div className="search-list-indicator">
                            {isSearchMode ? 'No results found' : 'No stocks available'}
                        </div>
                    ) : (
                        <ul>
                            <div className="search-count">
                                {isSearchMode ? 'Search results' : 'Popular stocks'}
                                {` `}({displayStocks?.length || 0})
                            </div>
                            {displayStocks?.map((stock) => (
                                <li key={stock.symbol} className="search-item">
                                    <Link
                                        href={`/stocks/${stock.symbol}`}
                                        onClick={handleSelectStock}
                                        className="search-item-link"
                                        prefetch={true}
                                    >
                                        <TrendingUp className="h-4 w-4 text-gray-500" />
                                        <div className="flex-1">
                                            <div className="search-item-name">
                                                {stock.name}
                                            </div>
                                            <div className="text-sm text-gray-500">
                                                {stock.symbol} | {stock.exchange } | {stock.type}
                                            </div>
                                        </div>
                                    </Link>
                                    <Link href={`/funds/${stock.symbol}`} prefetch={true}>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-8 w-8"
                                            title="Ver ficha detallada"
                                        >
                                            <ExternalLink className="h-4 w-4" />
                                        </Button>
                                    </Link>
                                </li>
                            ))}
                        </ul>
                    )
                    }
                </CommandList>
            </CommandDialog>
        </>
    )
}