import { Schema, model, models, type Document, type Model } from 'mongoose';

export interface Alert extends Document {
    _id: string;
    userId: string;
    symbol: string;
    type: 'price_above' | 'price_below' | 'price_change' | 'news' | 'earnings';
    condition: {
        operator: '>' | '<' | '>=' | '<=' | '==';
        value: number | string;
    };
    isActive: boolean;
    lastTriggered?: Date;
    createdAt: Date;
    updatedAt: Date;
}

const AlertSchema = new Schema<Alert>(
    {
        userId: { type: String, required: true, index: true },
        symbol: { type: String, required: true, uppercase: true, index: true },
        type: { 
            type: String, 
            required: true,
            enum: ['price_above', 'price_below', 'price_change', 'news', 'earnings']
        },
        condition: {
            operator: { type: String, required: true, enum: ['>', '<', '>=', '<=', '=='] },
            value: { type: Schema.Types.Mixed, required: true }
        },
        isActive: { type: Boolean, default: true, index: true },
        lastTriggered: { type: Date },
    },
    { timestamps: true }
);

AlertSchema.index({ userId: 1, isActive: 1 });
AlertSchema.index({ symbol: 1, isActive: 1 });

export const AlertModel: Model<Alert> =
    models?.Alert as Model<Alert> || model<Alert>('Alert', AlertSchema);

