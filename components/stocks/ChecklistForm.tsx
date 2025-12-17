'use client';

import { useState, useEffect } from 'react';
import { CHECKLIST_QUESTIONS } from '@/lib/checklist-questions';
import { saveChecklistAnswers, updateChecklistStatus, saveThesis } from '@/lib/actions/checklist.actions';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';

type AnswerType = 'yes' | 'no' | 'maybe' | 'unknown';
type StatusType = 'observando' | 'en_punto' | 'invertido' | 'descartado';

interface Answer {
    questionId: string;
    answer: AnswerType;
    notes?: string;
}

interface ChecklistFormProps {
    symbol: string;
    companyName: string;
    initialAnswers?: Answer[];
    initialThesis?: string;
    initialStatus?: StatusType;
    initialScore?: number;
}

const STATUS_LABELS: Record<StatusType, { label: string; color: string; emoji: string }> = {
    observando: { label: 'Observando', color: 'bg-yellow-500', emoji: '👀' },
    en_punto: { label: 'En Punto de Entrada', color: 'bg-green-500', emoji: '🎯' },
    invertido: { label: 'Invertido', color: 'bg-blue-500', emoji: '💰' },
    descartado: { label: 'Descartado', color: 'bg-gray-500', emoji: '❌' }
};

const ANSWER_BUTTONS: { value: AnswerType; label: string; color: string }[] = [
    { value: 'yes', label: 'Sí', color: 'bg-green-600 hover:bg-green-700' },
    { value: 'maybe', label: 'Quizás', color: 'bg-yellow-600 hover:bg-yellow-700' },
    { value: 'no', label: 'No', color: 'bg-red-600 hover:bg-red-700' },
    { value: 'unknown', label: '?', color: 'bg-gray-600 hover:bg-gray-700' }
];

export default function ChecklistForm({
    symbol,
    companyName,
    initialAnswers = [],
    initialThesis = '',
    initialStatus = 'observando',
    initialScore = 0
}: ChecklistFormProps) {
    // Inicializar respuestas
    const [answers, setAnswers] = useState<Record<string, Answer>>(() => {
        const map: Record<string, Answer> = {};
        CHECKLIST_QUESTIONS.forEach(q => {
            const existing = initialAnswers.find(a => a.questionId === q.id);
            map[q.id] = existing || { questionId: q.id, answer: 'unknown', notes: '' };
        });
        return map;
    });

    const [thesis, setThesis] = useState(initialThesis);
    const [status, setStatus] = useState<StatusType>(initialStatus);
    const [saving, setSaving] = useState(false);
    const [score, setScore] = useState(initialScore);

    // Calcular score cuando cambian las respuestas
    useEffect(() => {
        let totalScore = 0;
        let maxScore = 0;

        Object.values(answers).forEach(answer => {
            const question = CHECKLIST_QUESTIONS.find(q => q.id === answer.questionId);
            if (question) {
                maxScore += question.weight * 2;
                if (answer.answer === 'yes') {
                    totalScore += question.weight * 2;
                } else if (answer.answer === 'maybe') {
                    totalScore += question.weight * 1;
                }
            }
        });

        const pct = maxScore > 0 ? Math.round((totalScore / maxScore) * 100) : 0;
        setScore(pct);
    }, [answers]);

    // Guardar respuestas
    const handleSave = async () => {
        setSaving(true);
        try {
            const answersArray = Object.values(answers);
            await saveChecklistAnswers(symbol, answersArray);
            await updateChecklistStatus(symbol, status);
            if (thesis) {
                await saveThesis(symbol, thesis);
            }
        } catch (error) {
            console.error('Error saving:', error);
        }
        setSaving(false);
    };

    // Actualizar respuesta
    const updateAnswer = (questionId: string, answer: AnswerType) => {
        setAnswers(prev => ({
            ...prev,
            [questionId]: { ...prev[questionId], answer }
        }));
    };

    // Agrupar preguntas por categoría
    const groupedQuestions = CHECKLIST_QUESTIONS.reduce((acc, q) => {
        if (!acc[q.category]) acc[q.category] = [];
        acc[q.category].push(q);
        return acc;
    }, {} as Record<string, typeof CHECKLIST_QUESTIONS[number][]>);

    // Color del score
    const getScoreColor = () => {
        if (score >= 80) return 'text-green-400';
        if (score >= 65) return 'text-lime-400';
        if (score >= 45) return 'text-yellow-400';
        if (score >= 30) return 'text-orange-400';
        return 'text-red-400';
    };

    const getRecommendation = () => {
        if (score >= 80) return { text: 'COMPRA FUERTE', color: 'bg-green-600' };
        if (score >= 65) return { text: 'COMPRAR', color: 'bg-lime-600' };
        if (score >= 45) return { text: 'MANTENER', color: 'bg-yellow-600' };
        if (score >= 30) return { text: 'EVITAR', color: 'bg-orange-600' };
        return { text: 'EVITAR FUERTE', color: 'bg-red-600' };
    };

    return (
        <div className="space-y-6">
            {/* Header con Score */}
            <div className="flex items-center justify-between p-4 bg-gray-800 rounded-lg">
                <div>
                    <h2 className="text-2xl font-bold text-white">{symbol}</h2>
                    <p className="text-gray-400">{companyName}</p>
                </div>
                <div className="text-right">
                    <div className={`text-4xl font-bold ${getScoreColor()}`}>{score}%</div>
                    <Badge className={getRecommendation().color}>{getRecommendation().text}</Badge>
                </div>
            </div>

            {/* Status Selector */}
            <div className="p-4 bg-gray-800 rounded-lg">
                <h3 className="text-lg font-semibold text-white mb-3">Estado de la Inversión</h3>
                <div className="flex flex-wrap gap-2">
                    {(Object.keys(STATUS_LABELS) as StatusType[]).map(s => (
                        <Button
                            key={s}
                            variant={status === s ? 'default' : 'outline'}
                            className={status === s ? STATUS_LABELS[s].color : ''}
                            onClick={() => setStatus(s)}
                        >
                            {STATUS_LABELS[s].emoji} {STATUS_LABELS[s].label}
                        </Button>
                    ))}
                </div>
            </div>

            {/* Preguntas por Categoría */}
            {Object.entries(groupedQuestions).map(([category, questions]) => (
                <div key={category} className="p-4 bg-gray-800 rounded-lg">
                    <h3 className="text-lg font-semibold text-white mb-4 border-b border-gray-700 pb-2">
                        {category}
                    </h3>
                    <div className="space-y-4">
                        {questions.map(q => (
                            <div key={q.id} className="flex items-center justify-between gap-4 p-3 bg-gray-900 rounded">
                                <div className="flex-1">
                                    <p className="text-white">{q.question}</p>
                                    <span className="text-xs text-gray-500">Peso: {q.weight}x</span>
                                </div>
                                <div className="flex gap-1">
                                    {ANSWER_BUTTONS.map(btn => (
                                        <Button
                                            key={btn.value}
                                            size="sm"
                                            variant={answers[q.id]?.answer === btn.value ? 'default' : 'outline'}
                                            className={answers[q.id]?.answer === btn.value ? btn.color : ''}
                                            onClick={() => updateAnswer(q.id, btn.value)}
                                        >
                                            {btn.label}
                                        </Button>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            ))}

            {/* Tesis de Inversión */}
            <div className="p-4 bg-gray-800 rounded-lg">
                <h3 className="text-lg font-semibold text-white mb-3">Tu Tesis de Inversión</h3>
                <Textarea
                    value={thesis}
                    onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setThesis(e.target.value)}
                    placeholder="Escribe aquí tu tesis de inversión, razones para invertir, y puntos clave que justifican tu decisión..."
                    className="min-h-[150px] bg-gray-900 border-gray-700 text-white"
                />
            </div>

            {/* Botón Guardar */}
            <div className="flex justify-end">
                <Button
                    onClick={handleSave}
                    disabled={saving}
                    className="bg-blue-600 hover:bg-blue-700"
                >
                    {saving ? 'Guardando...' : '💾 Guardar Checklist'}
                </Button>
            </div>
        </div>
    );
}
