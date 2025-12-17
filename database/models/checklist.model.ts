import mongoose, { Schema, Document } from 'mongoose';
import { CHECKLIST_QUESTIONS } from '@/lib/checklist-questions';

// Re-export for backwards compatibility
export { CHECKLIST_QUESTIONS };

export interface IThesisChecklist extends Document {
    userId: string;
    symbol: string;
    companyName: string;
    answers: {
        questionId: string;
        answer: 'yes' | 'no' | 'maybe' | 'unknown';
        notes?: string;
    }[];
    totalScore: number;
    maxScore: number;
    percentageScore: number;
    recommendation: 'strong_buy' | 'buy' | 'hold' | 'avoid' | 'strong_avoid';
    thesis?: string;
    status: 'observando' | 'en_punto' | 'invertido' | 'descartado';
    createdAt: Date;
    updatedAt: Date;
}

const ThesisChecklistSchema = new Schema<IThesisChecklist>(
    {
        userId: { type: String, required: true, index: true },
        symbol: { type: String, required: true, uppercase: true },
        companyName: { type: String, required: true },
        answers: [{
            questionId: { type: String, required: true },
            answer: { type: String, enum: ['yes', 'no', 'maybe', 'unknown'], required: true },
            notes: { type: String }
        }],
        totalScore: { type: Number, default: 0 },
        maxScore: { type: Number, default: 0 },
        percentageScore: { type: Number, default: 0 },
        recommendation: {
            type: String,
            enum: ['strong_buy', 'buy', 'hold', 'avoid', 'strong_avoid'],
            default: 'hold'
        },
        thesis: { type: String },
        status: {
            type: String,
            enum: ['observando', 'en_punto', 'invertido', 'descartado'],
            default: 'observando'
        }
    },
    { timestamps: true }
);

// Índice único para un checklist por usuario por símbolo
ThesisChecklistSchema.index({ userId: 1, symbol: 1 }, { unique: true });

// Método para calcular score
ThesisChecklistSchema.methods.calculateScore = function () {
    let totalScore = 0;
    let maxScore = 0;

    for (const answer of this.answers) {
        const question = CHECKLIST_QUESTIONS.find(q => q.id === answer.questionId);
        if (question) {
            maxScore += question.weight * 2; // Max 2 puntos por pregunta (yes)
            if (answer.answer === 'yes') {
                totalScore += question.weight * 2;
            } else if (answer.answer === 'maybe') {
                totalScore += question.weight * 1;
            }
            // 'no' y 'unknown' = 0 puntos
        }
    }

    this.totalScore = totalScore;
    this.maxScore = maxScore;
    this.percentageScore = maxScore > 0 ? Math.round((totalScore / maxScore) * 100) : 0;

    // Determinar recomendación
    const pct = this.percentageScore;
    if (pct >= 80) this.recommendation = 'strong_buy';
    else if (pct >= 65) this.recommendation = 'buy';
    else if (pct >= 45) this.recommendation = 'hold';
    else if (pct >= 30) this.recommendation = 'avoid';
    else this.recommendation = 'strong_avoid';

    return this;
};

export const ThesisChecklist = mongoose.models.ThesisChecklist ||
    mongoose.model<IThesisChecklist>('ThesisChecklist', ThesisChecklistSchema);
