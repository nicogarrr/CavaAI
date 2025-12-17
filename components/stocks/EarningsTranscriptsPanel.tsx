'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { FileText, Loader2, Calendar } from 'lucide-react';
import { getEarningsTranscriptsList, getEarningsTranscriptContent, EarningsTranscript } from '@/lib/actions/fmp.actions';

interface EarningsTranscriptsPanelProps {
    symbol: string;
}

export default function EarningsTranscriptsPanel({ symbol }: EarningsTranscriptsPanelProps) {
    const [transcripts, setTranscripts] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedTranscript, setSelectedTranscript] = useState<EarningsTranscript | null>(null);
    const [loadingContent, setLoadingContent] = useState(false);
    const [isModalOpen, setIsModalOpen] = useState(false);

    useEffect(() => {
        const fetchList = async () => {
            setLoading(true);
            try {
                const data = await getEarningsTranscriptsList(symbol);
                setTranscripts(data);
            } catch (error) {
                console.error("Error fetching transcripts list:", error);
            } finally {
                setLoading(false);
            }
        };
        fetchList();
    }, [symbol]);

    const handleViewTranscript = async (dateStr: string) => {
        // Parse date to get year and quarter. 
        // FMP dates are usually "YYYY-MM-DD HH:MM:SS"
        const date = new Date(dateStr);
        const year = date.getFullYear();
        // Quarter inference is tricky from just date, but usually FMP list items might have it.
        // If the list item doesn't have year/quarter, we might need to rely on the date.
        // API documentation for `earning-call-transcript` (the content one) requires year and quarter.
        // Let's assume the list endpoint provides it or we have to guess.
        // Actually, the `earning-call-transcript` list endpoint returns objects like:
        // { "symbol": "AAPL", "date": "2020-07-30 17:00:00", "quarter": 3, "year": 2020 } (Hopefully)
        // If not, we might be in trouble. Let's inspect the data type in runtime if we could.
        // The endpoint used `v4/earning-call-transcript?symbol=...` usually returns just dates?
        // documentation says: "Available Transcript Symbols API" -> list of symbols.
        // "Transcripts Dates By Symbol API" -> list of dates [ "2021-10-28 17:00:00", ... ]
        // v4 endpoint usually returns objects. Let's check `data-engine/fmp.py` to see what we are fetching.
        // We are using `earning-call-transcript?symbol={symbol}` (v4).

        // Let's try to pass the item directly if it has quarter/year.
        // If the list is just objects with date, we will try to find the item in the state.
        const item = transcripts.find(t => t.date === dateStr);
        if (item && item.quarter && item.year) {
            setLoadingContent(true);
            setIsModalOpen(true);
            try {
                const content = await getEarningsTranscriptContent(symbol, item.year, item.quarter);
                setSelectedTranscript(content);
            } catch (e) {
                console.error(e);
            } finally {
                setLoadingContent(false);
            }
        } else {
            console.warn("Missing year/quarter for transcript", item);
            // Fallback: Estimate quarter from month?
            const month = date.getMonth() + 1;
            const q = Math.ceil(month / 3); // 1-3 -> Q1, 4-6 -> Q2... roughly
            // This is unreliable because fiscal years differ.
            // Better to alert user or rely on item properties.
            alert("No se pudo determinar el trimestre/año para esta transcripción.");
        }
    };

    if (loading) {
        return (
            <Card className="bg-[#1e293b] border-gray-700 h-full">
                <CardContent className="p-6 flex justify-center items-center h-full min-h-[300px]">
                    <Loader2 className="h-8 w-8 text-blue-400 animate-spin" />
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="bg-[#1e293b] border-gray-700 h-full flex flex-col">
            <CardHeader>
                <CardTitle className="text-xl font-bold text-gray-100 flex items-center gap-2">
                    <FileText className="h-5 w-5 text-blue-400" />
                    Transcripciones de Resultados
                </CardTitle>
            </CardHeader>
            <CardContent className="flex-1 overflow-hidden">
                <div className="h-[400px] pr-4 overflow-y-auto custom-scrollbar">
                    {transcripts.length === 0 ? (
                        <p className="text-gray-400 text-center py-10">No hay transcripciones disponibles.</p>
                    ) : (
                        <div className="space-y-3">
                            {transcripts.map((t, i) => (
                                <div key={i} className="flex items-center justify-between p-3 bg-gray-800/50 rounded-lg hover:bg-gray-800 transition-colors border border-gray-700">
                                    <div className="flex items-center gap-3">
                                        <div className="p-2 bg-blue-900/30 rounded-full">
                                            <Calendar className="h-4 w-4 text-blue-400" />
                                        </div>
                                        <div>
                                            <p className="text-gray-200 font-medium">
                                                {t.year ? `Q${t.quarter} ${t.year}` : new Date(t.date).getFullYear()}
                                            </p>
                                            <p className="text-xs text-gray-500">{new Date(t.date).toLocaleDateString()}</p>
                                        </div>
                                    </div>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => handleViewTranscript(t.date)}
                                        className="border-gray-600 hover:bg-gray-700 hover:text-white"
                                    >
                                        Leer
                                    </Button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </CardContent>

            <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
                <DialogContent className="bg-gray-900 border-gray-700 text-gray-100 max-w-4xl max-h-[85vh] flex flex-col">
                    <DialogHeader>
                        <DialogTitle className="text-xl flex items-center gap-2">
                            <FileText className="h-5 w-5 text-blue-400" />
                            {selectedTranscript ? `Q${selectedTranscript.quarter} ${selectedTranscript.year} Earnings Call` : 'Cargando...'}
                        </DialogTitle>
                    </DialogHeader>

                    <div className="flex-1 overflow-y-auto mt-4 p-4 bg-gray-800/50 rounded-lg border border-gray-700 font-mono text-sm leading-relaxed text-gray-300">
                        {loadingContent ? (
                            <div className="flex justify-center p-10">
                                <Loader2 className="h-8 w-8 text-blue-400 animate-spin" />
                            </div>
                        ) : selectedTranscript ? (
                            <div className="whitespace-pre-wrap">
                                {selectedTranscript.content}
                            </div>
                        ) : (
                            <p className="text-center text-gray-500">No se pudo cargar el contenido.</p>
                        )}
                    </div>
                </DialogContent>
            </Dialog>
        </Card>
    );
}
