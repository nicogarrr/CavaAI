'use client';

import { useState, useRef } from 'react';
import { Button } from '@/components/ui/button';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog';
import { Camera, Upload, Check, Loader2, Plus } from 'lucide-react';
import { extractPortfolioFromImage, type ExtractedPosition } from '@/lib/actions/ai.actions';
import { addTransaction } from '@/lib/actions/portfolio.actions';
import { useRouter } from 'next/navigation';

interface ImportFromImageProps {
    userId: string;
}

export default function ImportFromImage({ userId }: ImportFromImageProps) {
    const router = useRouter();
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [open, setOpen] = useState(false);
    const [loading, setLoading] = useState(false);
    const [imagePreview, setImagePreview] = useState<string | null>(null);
    const [extractedPositions, setExtractedPositions] = useState<ExtractedPosition[]>([]);
    const [selectedPositions, setSelectedPositions] = useState<Set<string>>(new Set());
    const [summary, setSummary] = useState('');
    const [detectedCurrency, setDetectedCurrency] = useState<'EUR' | 'USD'>('USD');
    const [error, setError] = useState('');
    const [importing, setImporting] = useState(false);

    const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (!files || files.length === 0) return;

        setLoading(true);
        setError('');

        let allPositions: ExtractedPosition[] = [];
        let summaryText = '';
        let detectedCurr: 'EUR' | 'USD' = 'USD';

        // Procesar cada archivo secuencialmente
        for (let i = 0; i < files.length; i++) {
            const file = files[i];

            // Crear promesa para leer el archivo
            const base64 = await new Promise<string>((resolve) => {
                const reader = new FileReader();
                reader.onload = (event) => resolve(event.target?.result as string);
                reader.readAsDataURL(file);
            });

            // Mostrar preview del último (o podríamos hacer un carrusel, pero por simplicidad el último)
            setImagePreview(base64);

            try {
                // Actualizar estado para mostrar progreso
                // (Podríamos agregar un estado de progreso UI si fuera necesario)

                const result = await extractPortfolioFromImage(base64);

                if (result.success) {
                    allPositions = [...allPositions, ...result.positions];
                    summaryText = result.summary; // Usamos el último resumen o concatenamos
                    detectedCurr = result.detectedCurrency;
                } else {
                    console.error(`Error en archivo ${i + 1}:`, result.error);
                }
            } catch (err) {
                console.error(`Excepción en archivo ${i + 1}`, err);
            }
        }

        if (allPositions.length > 0) {
            setExtractedPositions(prev => [...prev, ...allPositions]); // Añadir a las existentes? O reemplazar? Mejor reemplazar para evitar duplicados de intentos previos, pero el usuario pidió "lotes", tal vez quiera añadir. Resetear antes.
            // Decisión: Reemplazar lo anterior para un flujo limpio.
            // Espera, el usuario dijo "añadir mas de una captura en lotes".
            // Si subo 2, quiero ver todas.
            setExtractedPositions(allPositions);
            setSummary(`Procesadas ${files.length} imágenes. ${summaryText}`);
            setDetectedCurrency(detectedCurr);
            setSelectedPositions(new Set(allPositions.map(p => p.symbol)));
        } else {
            setError('No se pudieron extraer posiciones de las imágenes.');
        }

        setLoading(false);
    };

    const togglePosition = (symbol: string) => {
        const newSelected = new Set(selectedPositions);
        if (newSelected.has(symbol)) {
            newSelected.delete(symbol);
        } else {
            newSelected.add(symbol);
        }
        setSelectedPositions(newSelected);
    };

    const handleImport = async () => {
        setImporting(true);

        const positionsToImport = extractedPositions.filter(p => selectedPositions.has(p.symbol));

        for (const pos of positionsToImport) {
            let quantity = pos.shares || 0;
            let buyPrice = pos.currentPriceUSD || pos.currentPrice; // Por defecto

            // Si no tenemos cantidad (o es dudosa con precio muy alto), intentamos calcularla
            // O si el precio importado parece ser el valor total
            if (!quantity || quantity === 0) {
                try {
                    // Importar dinámicamente para no cargar en el cliente si no se usa
                    const { getStockQuote } = await import('@/lib/actions/finnhub.actions');
                    const quote = await getStockQuote(pos.symbol);

                    if (quote && quote.c > 0) {
                        const realPrice = quote.c;

                        // Si el precio importado es mucho mayor que el real (ej: > 2x), asumimos que es el VALOR TOTAL
                        // O si no tenemos shares definidos, asumimos que el valor capturado es el Market Value
                        // (En capturas de resumen suele ser Market Value)

                        // Calculamos shares basados en el valor total capturado / precio real
                        const detectedValue = pos.marketValue || pos.currentPriceUSD || 0;

                        if (detectedValue > 0) {
                            quantity = detectedValue / realPrice;

                            // AHORA: Calcular el precio de compra original (Average Price)
                            // Fórmula: Precio Compra = Precio Actual / (1 + (Porcentaje Ganancia / 100))
                            // Usamos el % de la captura que representa la rentabilidad total
                            if (pos.changePercent && pos.changePercent !== 0) {
                                buyPrice = realPrice / (1 + (pos.changePercent / 100));
                            } else {
                                // Si no hay porcentaje, usamos el precio actual (G/P será 0)
                                buyPrice = realPrice;
                            }
                        }
                    }
                } catch (e) {
                    console.error('Error fetching quote for calculation:', e);
                }
            }

            // Fallback si falla el cálculo
            if (quantity === 0) quantity = 1;

            await addTransaction(
                userId,
                pos.symbol,
                'buy',
                quantity,
                buyPrice,
                new Date(),
                `Importado desde captura - ${pos.name}`
            );
        }

        setImporting(false);
        setOpen(false);
        router.refresh();
    };

    const reset = () => {
        setImagePreview(null);
        setExtractedPositions([]);
        setSelectedPositions(new Set());
        setSummary('');
        setDetectedCurrency('USD');
        setError('');
    };

    return (
        <Dialog open={open} onOpenChange={(isOpen) => { setOpen(isOpen); if (!isOpen) reset(); }}>
            <DialogTrigger asChild>
                <Button variant="outline" className="flex items-center gap-2">
                    <Camera className="h-4 w-4" />
                    Importar desde Captura
                </Button>
            </DialogTrigger>
            <DialogContent className="bg-gray-900 border-gray-700 max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="text-gray-100">📷 Importar Cartera desde Captura</DialogTitle>
                    <DialogDescription className="text-gray-400">
                        Sube una o varias capturas de tu broker y la IA extraerá tus posiciones automáticamente
                    </DialogDescription>
                </DialogHeader>

                {!imagePreview ? (
                    <div
                        onClick={() => fileInputRef.current?.click()}
                        className="border-2 border-dashed border-gray-600 rounded-lg p-12 text-center cursor-pointer hover:border-teal-500 transition-colors"
                    >
                        <Upload className="h-12 w-12 mx-auto text-gray-500 mb-4" />
                        <p className="text-gray-300 mb-2">Haz click o arrastra tus imágenes</p>
                        <p className="text-gray-500 text-sm">Puedes seleccionar múltiples archivos</p>
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept="image/*"
                            multiple
                            onChange={handleFileSelect}
                            className="hidden"
                        />
                    </div>
                ) : (
                    <div className="space-y-4">
                        {/* Preview de imagen */}
                        <div className="relative">
                            <img
                                src={imagePreview}
                                alt="Captura de cartera"
                                className="w-full rounded-lg max-h-48 object-cover"
                            />
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={reset}
                                className="absolute top-2 right-2"
                            >
                                Cambiar imagen
                            </Button>
                        </div>

                        {/* Loading */}
                        {loading && (
                            <div className="flex items-center justify-center py-8">
                                <Loader2 className="h-8 w-8 animate-spin text-teal-500" />
                                <span className="ml-3 text-gray-400">Analizando imagen con IA...</span>
                            </div>
                        )}

                        {/* Error */}
                        {error && (
                            <div className="p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-300">
                                {error}
                            </div>
                        )}

                        {/* Resultados */}
                        {!loading && extractedPositions.length > 0 && (
                            <>
                                <div className="p-3 bg-teal-900/30 border border-teal-700 rounded-lg">
                                    <p className="text-teal-300 text-sm">{summary}</p>
                                </div>

                                <div className="space-y-2">
                                    <p className="text-gray-300 font-medium">
                                        Posiciones encontradas ({extractedPositions.length}):
                                    </p>
                                    {extractedPositions.map((pos) => (
                                        <div
                                            key={pos.symbol}
                                            onClick={() => togglePosition(pos.symbol)}
                                            className={`flex items-center justify-between p-3 rounded-lg cursor-pointer transition-colors ${selectedPositions.has(pos.symbol)
                                                ? 'bg-teal-900/40 border border-teal-600'
                                                : 'bg-gray-800 border border-gray-700'
                                                }`}
                                        >
                                            <div className="flex items-center gap-3">
                                                <div className={`w-5 h-5 rounded flex items-center justify-center ${selectedPositions.has(pos.symbol) ? 'bg-teal-500' : 'bg-gray-700'
                                                    }`}>
                                                    {selectedPositions.has(pos.symbol) && <Check className="w-3 h-3 text-white" />}
                                                </div>
                                                <div>
                                                    <span className="text-white font-medium">{pos.symbol}</span>
                                                    <span className="text-gray-400 text-sm ml-2">{pos.name}</span>
                                                </div>
                                            </div>
                                            <div className="text-right">
                                                <div className="text-white flex items-center gap-1">
                                                    {pos.currency === 'EUR' && <span className="text-xs text-yellow-400">€{pos.currentPrice.toFixed(2)} →</span>}
                                                    ${pos.currentPriceUSD?.toFixed(2) || pos.currentPrice.toFixed(2)}
                                                </div>
                                                <div className={`text-sm ${pos.changePercent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                    {pos.changePercent >= 0 ? '+' : ''}{pos.changePercent.toFixed(2)}%
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                <div className="flex justify-end gap-2 pt-4">
                                    <Button variant="outline" onClick={() => setOpen(false)}>
                                        Cancelar
                                    </Button>
                                    <Button
                                        onClick={handleImport}
                                        disabled={importing || selectedPositions.size === 0}
                                        className="bg-teal-600 hover:bg-teal-700"
                                    >
                                        {importing ? (
                                            <>
                                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                                Importando...
                                            </>
                                        ) : (
                                            <>
                                                <Plus className="w-4 h-4 mr-2" />
                                                Importar {selectedPositions.size} posiciones
                                            </>
                                        )}
                                    </Button>
                                </div>
                            </>
                        )}
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}
