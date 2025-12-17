'use client';

import { useState } from 'react';
import { generateChecklistWithAI } from '@/lib/actions/ai.actions';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

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
    understand_business: '¿Entiendo cómo gana dinero?',
    competitive_moat: '¿Tiene ventaja competitiva (moat)?',
    pricing_power: '¿Puede subir precios?',
    recurring_revenue: '¿Ingresos recurrentes?',
    management_quality: '¿Management competente?',
    skin_in_game: '¿Directivos con participación?',
    debt_level: '¿Deuda manejable?',
    free_cash_flow: '¿Free Cash Flow positivo?',
    return_on_capital: '¿ROIC/ROE > 15%?',
    margin_of_safety: '¿Margen de seguridad > 25%?',
    growth_potential: '¿Potencial de crecimiento?',
    industry_tailwinds: '¿Sector favorable?',
    no_major_risks: '¿Riesgos manejables?',
    capital_allocation: '¿Buena asignación de capital?',
    would_hold_10_years: '¿Mantendría 10 años?'
};

const ANSWER_COLORS = {
    yes: 'bg-green-600',
    no: 'bg-red-600',
    maybe: 'bg-yellow-600'
};

const ANSWER_LABELS = {
    yes: '✅ Sí',
    no: '❌ No',
    maybe: '⚠️ Quizás'
};

export default function AIChecklistSection({
    symbol,
    companyName,
    financialData,
    currentPrice
}: AIChecklistSectionProps) {
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<{
        answers: ChecklistAnswer[];
        overallScore: number;
        recommendation: string;
        summary: string;
    } | null>(null);
    const [expanded, setExpanded] = useState(false);

    const loadChecklist = async () => {
        setLoading(true);
        try {
            const data = await generateChecklistWithAI({
                symbol,
                companyName,
                // financialData, // Evitar enviar payload gigante al server action
                currentPrice
            });
            setResult(data);
            setExpanded(true);
        } catch (error) {
            console.error('Error loading AI checklist:', error);
        }
        setLoading(false);
    };

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

    if (!result && !loading) {
        return (
            <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-6">
                <div className="flex items-center justify-between">
                    <div>
                        <h2 className="text-xl font-bold text-white flex items-center gap-2">
                            🤖 Análisis Value Investing (IA)
                        </h2>
                        <p className="text-gray-400 text-sm mt-1">
                            15 preguntas clave respondidas automáticamente por IA basándose en datos financieros reales
                        </p>
                    </div>
                    <Button
                        onClick={loadChecklist}
                        className="bg-blue-600 hover:bg-blue-700"
                    >
                        ✨ Generar Análisis
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
                    <span className="ml-3 text-gray-400">Analizando con IA las 15 preguntas clave...</span>
                </div>
            </div>
        );
    }

    return (
        <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-6 space-y-4">
            {/* Header con Score */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-xl font-bold text-white flex items-center gap-2">
                        🤖 Análisis Value Investing - {symbol}
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
                <span className="text-green-400">✅ {yesCount} Sí</span>
                <span className="text-yellow-400">⚠️ {maybeCount} Quizás</span>
                <span className="text-red-400">❌ {noCount} No</span>
            </div>

            {/* Detailed Answers */}
            {expanded && result?.answers && (
                <div className="space-y-2 mt-4">
                    {result.answers.map((answer) => (
                        <div
                            key={answer.questionId}
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
                    🔄 Regenerar Análisis
                </Button>
            </div>
        </div>
    );
}
