'use client';

import { useState, useEffect } from 'react';
import { getOrCreateChecklist } from '@/lib/actions/checklist.actions';
import ChecklistForm from './ChecklistForm';
import { Button } from '@/components/ui/button';

interface ChecklistSectionProps {
    symbol: string;
    companyName: string;
}

export default function ChecklistSection({ symbol, companyName }: ChecklistSectionProps) {
    const [isOpen, setIsOpen] = useState(false);
    const [checklist, setChecklist] = useState<any>(null);
    const [loading, setLoading] = useState(false);

    const loadChecklist = async () => {
        setLoading(true);
        try {
            const data = await getOrCreateChecklist(symbol, companyName);
            setChecklist(data);
        } catch (error) {
            console.error('Error loading checklist:', error);
        }
        setLoading(false);
    };

    useEffect(() => {
        if (isOpen && !checklist) {
            loadChecklist();
        }
    }, [isOpen]);

    if (!isOpen) {
        return (
            <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-6">
                <div className="flex items-center justify-between">
                    <div>
                        <h2 className="text-xl font-bold text-white flex items-center gap-2">
                            📋 Checklist de Inversión
                        </h2>
                        <p className="text-gray-400 text-sm mt-1">
                            15 preguntas clave para evaluar esta inversión con metodología Value Investing
                        </p>
                    </div>
                    <Button
                        onClick={() => setIsOpen(true)}
                        className="bg-blue-600 hover:bg-blue-700"
                    >
                        Abrir Checklist
                    </Button>
                </div>
            </div>
        );
    }

    if (loading) {
        return (
            <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-6">
                <div className="flex items-center justify-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                    <span className="ml-3 text-gray-400">Cargando checklist...</span>
                </div>
            </div>
        );
    }

    return (
        <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-6">
            <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                    📋 Checklist de Inversión - {symbol}
                </h2>
                <Button
                    variant="outline"
                    onClick={() => setIsOpen(false)}
                >
                    Cerrar
                </Button>
            </div>

            {checklist && (
                <ChecklistForm
                    symbol={symbol}
                    companyName={companyName}
                    initialAnswers={checklist.answers}
                    initialThesis={checklist.thesis}
                    initialStatus={checklist.status}
                    initialScore={checklist.percentageScore}
                />
            )}
        </div>
    );
}
