import { Schema, model, models, type Document, type Model } from 'mongoose';

export interface PortfolioTransaction extends Document {
    userId: string;
    symbol: string;
    type: 'buy' | 'sell';
    quantity: number;
    price: number;
    date: Date;
    notes?: string;
    createdAt: Date;
    updatedAt: Date;
}

const PortfolioTransactionSchema = new Schema<PortfolioTransaction>(
    {
        userId: { type: String, required: true, index: true },
        symbol: { type: String, required: true, uppercase: true, trim: true, index: true },
        type: { type: String, required: true, enum: ['buy', 'sell'] },
        quantity: { type: Number, required: true, min: 0 },
        price: { type: Number, required: true, min: 0 },
        date: { type: Date, required: true, default: Date.now, index: true },
        notes: { type: String, trim: true },
    },
    { timestamps: true }
);

PortfolioTransactionSchema.index({ userId: 1, symbol: 1 });
PortfolioTransactionSchema.index({ userId: 1, date: -1 });

// Índices adicionales recomendados
PortfolioTransactionSchema.index({ userId: 1, updatedAt: -1 });

export const PortfolioTransaction: Model<PortfolioTransaction> =
    (models?.PortfolioTransaction as Model<PortfolioTransaction>) || 
    model<PortfolioTransaction>('PortfolioTransaction', PortfolioTransactionSchema);
