import { Schema, model, models, type Document, type Model } from 'mongoose';

export interface SavedScreener extends Document {
    userId: string;
    name: string;
    description?: string;
    filters: {
        marketCapMin: number;
        marketCapMax: number;
        priceMin: number;
        priceMax: number;
        peMin: number;
        peMax: number;
        pbMin: number;
        pbMax: number;
        roeMin: number;
        roeMax: number;
        volumeMin: number;
        betaMin: number;
        betaMax: number;
        sector: string;
        exchange: string;
        assetType: string;
        sortBy: string;
        sortOrder: 'asc' | 'desc';
    };
    createdAt: Date;
    updatedAt: Date;
}

const SavedScreenerSchema = new Schema<SavedScreener>(
    {
        userId: { type: String, required: true, index: true },
        name: { type: String, required: true, trim: true },
        description: { type: String, trim: true },
        filters: {
            type: Schema.Types.Mixed,
            required: true,
        },
    },
    { timestamps: true }
);

SavedScreenerSchema.index({ userId: 1, name: 1 }, { unique: true });

export const SavedScreenerModel: Model<SavedScreener> =
    (models?.SavedScreener as Model<SavedScreener>) || model<SavedScreener>('SavedScreener', SavedScreenerSchema);
