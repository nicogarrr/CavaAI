'use client';

import { useState, useEffect } from 'react';
import { generateChecklistWithAI } from '@/lib/actions/ai.actions';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, RefreshCw } from 'lucide-react';

interface AIChecklistSectionProps {
    symbol: string;
    companyName: string;
    financialData: any;
    currentPrice: number;
}

interface ChecklistAnswer {
    questionId: string;
    answer: 'yes' | 'no' | 'maybe';
    explanation: string;
}

const QUESTION_LABELS: Record<string, string> = {
    // Negocio y Moat
    understand_business: '¿Entiendo el modelo de negocio?',
    competitive_moat: '¿Tiene ventaja competitiva (moat)?',
    pricing_power: '¿Poder de fijación de precios?',
    recurring_revenue: '¿Ingresos recurrentes?',
    // Management
    management_quality: '¿Management competente?',
    skin_in_game: '¿Directivos con participación?',
    insider_buying: '¿Compras de insiders recientes?',
    capital_allocation: '¿Buena asignación de capital?',
    // Calidad Financiera
    earnings_quality: '¿Calidad de beneficios (FCF/NI)?',
    free_cash_flow: '¿Free Cash Flow positivo?',
    return_on_capital: '¿ROIC > 12%?',
    margin_stability: '¿Márgenes estables/crecientes?',
    // Balance y Riesgo
    debt_level: '¿Deuda manejable (< 2x EBITDA)?',
    strong_balance: '¿Balance sólido?',
    no_major_risks: '¿Riesgos manejables?',
    // Valoración
    margin_of_safety: '¿Margen de seguridad > 20%?',
    valuation_vs_history: '¿Valoración < media histórica?',
    // Crecimiento y Sector
    growth_potential: '¿Potencial de crecimiento?',
    industry_tailwinds: '¿Sector favorable?',
    // Convicción
    would_hold_10_years: '¿Mantendría 10 años?'
};

const ANSWER_COLORS = {
    yes: 'bg-green-600',
    no: 'bg-red-600',
    maybe: 'bg-yellow-600'
};

const ANSWER_LABELS = {
    yes: 'Sí',
    no: 'No',
    maybe: 'Quizás'
};

export default function AIChecklistSection({
    symbol,
    companyName,
    financialData,
    currentPrice
}: AIChecklistSectionProps) {
    const [loading, setLoading] = useState(true);
    const [result, setResult] = useState<{
        answers: ChecklistAnswer[];
        overallScore: number;
        recommendation: string;
        summary: string;
    } | null>(null);
    const [expanded, setExpanded] = useState(true);

    const loadChecklist = async () => {
        setLoading(true);
        try {
            const data = await generateChecklistWithAI({
                symbol,
                companyName,
                currentPrice
            });
            setResult(data);
        } catch (error) {
            console.error('Error loading AI checklist:', error);
        }
        setLoading(false);
    };

    // Auto-execute on mount
    useEffect(() => {
        loadChecklist();
    }, [symbol]);

    const getScoreColor = (score: number) => {
        if (score >= 80) return 'text-green-400';
        if (score >= 65) return 'text-lime-400';
        if (score >= 45) return 'text-yellow-400';
        if (score >= 30) return 'text-orange-400';
        return 'text-red-400';
    };

    const getRecommendationColor = (rec: string) => {
        if (rec.includes('FUERTE') && rec.includes('COMPRA')) return 'bg-green-600';
        if (rec.includes('COMPRAR')) return 'bg-lime-600';
        if (rec.includes('MANTENER')) return 'bg-yellow-600';
        if (rec.includes('EVITAR') && rec.includes('FUERTE')) return 'bg-red-600';
        if (rec.includes('EVITAR')) return 'bg-orange-600';
        return 'bg-gray-600';
    };

    // Stats
    const yesCount = result?.answers.filter(a => a.answer === 'yes').length || 0;
    const noCount = result?.answers.filter(a => a.answer === 'no').length || 0;
    const maybeCount = result?.answers.filter(a => a.answer === 'maybe').length || 0;

    if (loading) {
        return (
            <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-6">
                <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
                    <span className="ml-3 text-gray-400">Analizando las 20 preguntas clave del value investing...</span>
                </div>
            </div>
        );
    }

    if (!result) {
        return (
            <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-6">
                <p className="text-gray-400">No se pudo cargar el análisis</p>
            </div>
        );
    }

    return (
        <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-6 space-y-4">
            {/* Header con Score */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-xl font-bold text-white flex items-center gap-2">
                        Análisis Value Investing (IA)
                    </h2>
                </div>
                <div className="text-right flex items-center gap-4">
                    <div>
                        <div className={`text-3xl font-bold ${getScoreColor(result?.overallScore || 0)}`}>
                            {result?.overallScore}%
                        </div>
                        <Badge className={getRecommendationColor(result?.recommendation || '')}>
                            {result?.recommendation}
                        </Badge>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => setExpanded(!expanded)}>
                        {expanded ? '▲ Colapsar' : '▼ Expandir'}
                    </Button>
                </div>
            </div>

            {/* Summary */}
            <div className="p-4 bg-gray-900 rounded-lg">
                <p className="text-gray-300">{result?.summary}</p>
            </div>

            {/* Quick Stats */}
            <div className="flex gap-4 text-sm">
                <span className="text-green-400">{yesCount} Sí</span>
                <span className="text-yellow-400">{maybeCount} Quizás</span>
                <span className="text-red-400">{noCount} No</span>
            </div>

            {/* Detailed Answers */}
            {expanded && result?.answers && (
                <div className="space-y-2 mt-4">
                    {result.answers.map((answer, index) => (
                        <div
                            key={`${answer.questionId}-${index}`}
                            className="flex items-start gap-3 p-3 bg-gray-900 rounded-lg"
                        >
                            <Badge className={`${ANSWER_COLORS[answer.answer]} shrink-0`}>
                                {ANSWER_LABELS[answer.answer]}
                            </Badge>
                            <div className="flex-1">
                                <p className="text-white font-medium">
                                    {QUESTION_LABELS[answer.questionId] || answer.questionId}
                                </p>
                                <p className="text-gray-400 text-sm mt-1">{answer.explanation}</p>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Regenerate Button */}
            <div className="flex justify-end pt-2">
                <Button
                    onClick={loadChecklist}
                    variant="outline"
                    size="sm"
                >
                    <RefreshCw className="h-4 w-4 mr-1" /> Regenerar
                </Button>
            </div>
        </div>
    );
}
