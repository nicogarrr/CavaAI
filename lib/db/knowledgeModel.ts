/**
 * MongoDB Knowledge Base Model
 * Usa MongoDB Atlas Vector Search para RAG
 */

import mongoose, { Schema, Document, Model } from 'mongoose';

export interface IKnowledgeDocument extends Document {
    title: string;
    content: string;
    embedding: number[];
    metadata: {
        source?: string;
        symbol?: string;
        tags?: string[];
        fileType?: string;
        chunkIndex?: number;
        totalChunks?: number;
    };
    preview: string;
    createdAt: Date;
    updatedAt: Date;
}

const KnowledgeSchema = new Schema<IKnowledgeDocument>(
    {
        title: {
            type: String,
            required: true,
            index: true,
        },
        content: {
            type: String,
            required: true,
        },
        embedding: {
            type: [Number],
            required: true,
            // Vector de 768 dimensiones para text-embedding-004
        },
        metadata: {
            source: String,
            symbol: { type: String, index: true },
            tags: [String],
            fileType: String,
            chunkIndex: Number,
            totalChunks: Number,
        },
        preview: {
            type: String,
            required: true,
        },
    },
    {
        timestamps: true,
        collection: 'knowledge_docs',
    }
);

// Índice de texto para búsqueda tradicional
KnowledgeSchema.index({ content: 'text', title: 'text' });

// Verificar si el modelo ya existe antes de crearlo
let KnowledgeModel: Model<IKnowledgeDocument>;

try {
    KnowledgeModel = mongoose.model<IKnowledgeDocument>('Knowledge');
} catch {
    KnowledgeModel = mongoose.model<IKnowledgeDocument>('Knowledge', KnowledgeSchema);
}

export { KnowledgeModel };

/**
 * IMPORTANTE: Para habilitar búsqueda vectorial, necesitas crear un índice en MongoDB Atlas:
 * 
 * 1. Ve a tu cluster en MongoDB Atlas
 * 2. Click en "Atlas Search" en el menú lateral
 * 3. Click en "Create Search Index"
 * 4. Selecciona "JSON Editor"
 * 5. Usa esta configuración:
 * 
 * {
 *   "mappings": {
 *     "dynamic": true,
 *     "fields": {
 *       "embedding": {
 *         "dimensions": 768,
 *         "similarity": "cosine",
 *         "type": "knnVector"
 *       }
 *     }
 *   }
 * }
 * 
 * 6. Nombre del índice: "vector_index"
 * 7. Colección: "knowledge_docs"
 */

