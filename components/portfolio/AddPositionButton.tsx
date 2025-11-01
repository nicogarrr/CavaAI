'use client';

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Plus, Search } from 'lucide-react';
import { addPosition } from '@/lib/actions/portfolio.actions';
import { searchStocks } from '@/lib/actions/finnhub.actions';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';

type AddPositionButtonProps = {
    portfolioId: string;
};

type SearchResult = {
    symbol: string;
    description: string;
    type: string;
};

export default function AddPositionButton({ portfolioId }: AddPositionButtonProps) {
    const [open, setOpen] = useState(false);
    const [symbol, setSymbol] = useState('');
    const [company, setCompany] = useState('');
    const [shares, setShares] = useState('');
    const [avgPurchasePrice, setAvgPurchasePrice] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
    const [isSearching, setIsSearching] = useState(false);
    const router = useRouter();
    const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const abortControllerRef = useRef<AbortController | null>(null);

    // Buscar acciones en Finnhub con debounce y cancelación
    useEffect(() => {
        // Limpiar timeout anterior
        if (searchTimeoutRef.current) {
            clearTimeout(searchTimeoutRef.current);
        }

        // Cancelar request anterior
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }

        if (searchQuery.trim().length < 1) {
            setSearchResults([]);
            setIsSearching(false);
            return;
        }

        setIsSearching(true);
        const trimmedQuery = searchQuery.trim();

        // Crear nuevo AbortController para esta búsqueda
        const controller = new AbortController();
        abortControllerRef.current = controller;

        searchTimeoutRef.current = setTimeout(async () => {
            try {
                // Usar server action en lugar de fetch directo
                const results = await searchStocks(trimmedQuery);
                
                // Solo actualizar si el request no fue cancelado
                if (!controller.signal.aborted && results) {
                    const mapped: SearchResult[] = results.slice(0, 5).map((stock: any) => ({
                        symbol: stock.symbol || '',
                        description: stock.name || stock.description || '',
                        type: stock.type || 'Stock',
                    }));
                    setSearchResults(mapped);
                }
            } catch (error: any) {
                // Ignorar errores de cancelación
                if (error?.name !== 'AbortError' && !controller.signal.aborted) {
                    console.error('Error buscando acciones:', error);
                    setSearchResults([]);
                }
            } finally {
                if (!controller.signal.aborted) {
                    setIsSearching(false);
                }
            }
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
    }, [searchQuery]);

    const handleSelectStock = useCallback(async (result: SearchResult) => {
        setSymbol(result.symbol);
        setCompany(result.description);
        setSearchQuery('');
        setSearchResults([]);

        // Obtener precio actual automáticamente usando server action
        try {
            const response = await fetch(`/api/quote?symbol=${encodeURIComponent(result.symbol)}`, {
                method: 'GET',
                cache: 'no-store',
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.currentPrice && data.currentPrice > 0) {
                    setAvgPurchasePrice(data.currentPrice.toFixed(2));
                    toast.success(`Precio actual de ${result.symbol}: $${data.currentPrice.toFixed(2)}`);
                }
            }
        } catch (error) {
            console.error('Error obteniendo precio:', error);
        }
    }, []);

    const handleSubmit = useCallback(async (e: React.FormEvent) => {
        e.preventDefault();

        if (!symbol.trim() || !company.trim() || !shares || !avgPurchasePrice) {
            toast.error('Todos los campos son requeridos');
            return;
        }

        const sharesNum = parseFloat(shares);
        const priceNum = parseFloat(avgPurchasePrice);

        if (isNaN(sharesNum) || sharesNum <= 0) {
            toast.error('La cantidad de acciones debe ser mayor a 0');
            return;
        }

        if (isNaN(priceNum) || priceNum <= 0) {
            toast.error('El precio debe ser mayor a 0');
            return;
        }

        setIsLoading(true);

        try {
            await addPosition(portfolioId, {
                symbol: symbol.trim().toUpperCase(),
                company: company.trim(),
                shares: sharesNum,
                avgPurchasePrice: priceNum,
            });
            toast.success('Posición añadida correctamente');
            setSymbol('');
            setCompany('');
            setShares('');
            setAvgPurchasePrice('');
            setOpen(false);
            router.refresh();
        } catch (error) {
            console.error('Error al añadir posición:', error);
            toast.error('Error al añadir la posición');
        } finally {
            setIsLoading(false);
        }
    }, [symbol, company, shares, avgPurchasePrice, portfolioId, router]);

    // Limpiar formulario cuando se cierra el modal
    useEffect(() => {
        if (!open) {
            setSymbol('');
            setCompany('');
            setShares('');
            setAvgPurchasePrice('');
            setSearchQuery('');
            setSearchResults([]);
            // Limpiar timeouts y cancelar requests
            if (searchTimeoutRef.current) {
                clearTimeout(searchTimeoutRef.current);
            }
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
        }
    }, [open]);

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button>
                    <Plus className="mr-2 h-4 w-4" />
                    Añadir Posición
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle>Añadir Nueva Posición</DialogTitle>
                </DialogHeader>
                <form onSubmit={handleSubmit} className="space-y-4">
                    {/* Buscador de acciones */}
                    <div className="relative">
                        <Label htmlFor="search">Buscar Acción o ETF</Label>
                        <div className="relative">
                            <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                            <Input
                                id="search"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                placeholder="Buscar por símbolo o nombre (ej: AAPL, Microsoft, SPY)..."
                                className="pl-10"
                            />
                        </div>
                        
                        {/* Resultados de búsqueda */}
                        {searchResults.length > 0 && (
                            <div className="absolute z-50 w-full mt-2 bg-background border rounded-md shadow-lg max-h-60 overflow-y-auto">
                                {searchResults.map((result) => (
                                    <button
                                        key={result.symbol}
                                        type="button"
                                        onClick={() => handleSelectStock(result)}
                                        className="w-full px-4 py-3 text-left hover:bg-muted transition-colors flex items-center gap-3 border-b last:border-b-0"
                                    >
                                        <div className="flex-1">
                                            <div className="font-medium">{result.symbol}</div>
                                            <div className="text-sm text-muted-foreground line-clamp-1">
                                                {result.description}
                                            </div>
                                        </div>
                                        <div className="text-xs px-2 py-1 bg-muted rounded">
                                            {result.type}
                                        </div>
                                    </button>
                                ))}
                            </div>
                        )}
                        
                        {isSearching && (
                            <div className="text-sm text-muted-foreground mt-2">
                                Buscando...
                            </div>
                        )}
                    </div>

                    <div className="border-t pt-4">
                        <p className="text-sm text-muted-foreground mb-4">
                            O introduce manualmente los datos:
                        </p>
                    </div>

                    <div>
                        <Label htmlFor="symbol">Símbolo *</Label>
                        <Input
                            id="symbol"
                            value={symbol}
                            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                            placeholder="AAPL"
                            required
                        />
                    </div>
                    <div>
                        <Label htmlFor="company">Compañía *</Label>
                        <Input
                            id="company"
                            value={company}
                            onChange={(e) => setCompany(e.target.value)}
                            placeholder="Apple Inc."
                            required
                        />
                    </div>
                    <div>
                        <Label htmlFor="shares">Cantidad de Acciones *</Label>
                        <Input
                            id="shares"
                            type="number"
                            step="0.01"
                            min="0.01"
                            value={shares}
                            onChange={(e) => setShares(e.target.value)}
                            placeholder="10"
                            required
                        />
                    </div>
                    <div>
                        <Label htmlFor="avgPurchasePrice">Precio de Compra (USD) *</Label>
                        <Input
                            id="avgPurchasePrice"
                            type="number"
                            step="0.01"
                            min="0.01"
                            value={avgPurchasePrice}
                            onChange={(e) => setAvgPurchasePrice(e.target.value)}
                            placeholder="150.00"
                            required
                        />
                    </div>
                    <div className="flex justify-end gap-2">
                        <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                            Cancelar
                        </Button>
                        <Button type="submit" disabled={isLoading}>
                            {isLoading ? 'Añadiendo...' : 'Añadir'}
                        </Button>
                    </div>
                </form>
            </DialogContent>
        </Dialog>
    );
}

