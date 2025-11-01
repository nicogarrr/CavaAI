import { Schema, model, models, type Document, type Model } from 'mongoose';

export interface PortfolioPosition {
    symbol: string;
    company: string;
    shares: number;
    avgPurchasePrice: number;
    purchaseDate: Date;
}

export interface Portfolio extends Document {
    _id: string;
    userId: string;
    name: string;
    description?: string;
    positions: PortfolioPosition[];
    createdAt: Date;
    updatedAt: Date;
}

const PositionSchema = new Schema<PortfolioPosition>(
    {
        symbol: { type: String, required: true, uppercase: true, trim: true },
        company: { type: String, required: true, trim: true },
        shares: { type: Number, required: true, min: 0 },
        avgPurchasePrice: { type: Number, required: true, min: 0 },
        purchaseDate: { type: Date, default: Date.now },
    },
    { _id: false }
);

const PortfolioSchema = new Schema<Portfolio>(
    {
        userId: { type: String, required: true, index: true },
        name: { type: String, required: true, trim: true },
        description: { type: String, trim: true },
        positions: [PositionSchema],
        createdAt: { type: Date, default: Date.now },
        updatedAt: { type: Date, default: Date.now },
    },
    { timestamps: true }
);

// Index for faster user-specific queries
PortfolioSchema.index({ userId: 1, name: 1 });

export const PortfolioModel: Model<Portfolio> =
    (models?.Portfolio as Model<Portfolio>) || model<Portfolio>('Portfolio', PortfolioSchema);

