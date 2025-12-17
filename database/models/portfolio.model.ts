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

// ============================================
// Modelo de Portfolio (posiciones consolidadas)
// ============================================

export interface IPosition {
    symbol: string;
    companyName: string;
    shares: number;
    avgPrice: number;
    purchaseDate: Date;
    notes?: string;
}

export interface IPortfolio extends Document {
    userId: string;
    positions: IPosition[];
    createdAt: Date;
    updatedAt: Date;
}

const PositionSchema = new Schema<IPosition>({
    symbol: { type: String, required: true },
    companyName: { type: String, required: true },
    shares: { type: Number, required: true, min: 0 },
    avgPrice: { type: Number, required: true, min: 0 },
    purchaseDate: { type: Date, required: true, default: Date.now },
    notes: { type: String }
});

const PortfolioSchema = new Schema<IPortfolio>(
    {
        userId: { type: String, required: true, unique: true, index: true },
        positions: { type: [PositionSchema], default: [] }
    },
    { timestamps: true, collection: 'portfolios' }
);

PortfolioSchema.index({ 'positions.symbol': 1 });

export const Portfolio: Model<IPortfolio> =
    (models?.Portfolio as Model<IPortfolio>) ||
    model<IPortfolio>('Portfolio', PortfolioSchema);
