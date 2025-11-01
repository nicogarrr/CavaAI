import { Schema, model, models, type Document, type Model } from 'mongoose';

export interface FamousInvestor extends Document {
    _id: string;
    name: string;
    description: string;
    image?: string;
    positions: Array<{
        symbol: string;
        company: string;
        shares?: number;
        value?: number;
        percentage?: number;
        source?: string; // '13F' | 'public' | 'estimated'
    }>;
    lastUpdated: Date;
    totalValue?: number;
    createdAt: Date;
    updatedAt: Date;
}

const PositionSchema = new Schema(
    {
        symbol: { type: String, required: true, uppercase: true },
        company: { type: String, required: true },
        shares: { type: Number },
        value: { type: Number },
        percentage: { type: Number },
        source: { type: String, enum: ['13F', 'public', 'estimated'] }
    },
    { _id: false }
);

const FamousInvestorSchema = new Schema<FamousInvestor>(
    {
        name: { type: String, required: true, unique: true },
        description: { type: String, required: true },
        image: { type: String },
        positions: [PositionSchema],
        lastUpdated: { type: Date, default: Date.now },
        totalValue: { type: Number },
    },
    { timestamps: true }
);

export const FamousInvestorModel: Model<FamousInvestor> =
    models?.FamousInvestor as Model<FamousInvestor> || 
    model<FamousInvestor>('FamousInvestor', FamousInvestorSchema);

