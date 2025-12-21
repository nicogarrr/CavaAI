'use server';

import { connectToDatabase } from '@/database/mongoose';
import { KnowledgeModel, IKnowledgeDocument } from '@/lib/db/knowledgeModel';
import { GoogleGenerativeAI } from '@google/generative-ai';

// Inicializar Gemini para embeddings
const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY || '');

/**
 * Genera embeddings usando Gemini
 */
async function generateEmbedding(text: string): Promise<number[]> {
    try {
        const model = genAI.getGenerativeModel({ model: 'text-embedding-004' });
        const result = await model.embedContent(text);
        return result.embedding.values;
    } catch (error) {
        console.error('Error generating embedding:', error);
        // Fallback: vector de ceros (no ideal, pero evita errores)
        return new Array(768).fill(0);
    }
}

/**
 * Divide texto en chunks para mejor búsqueda
 */
function chunkText(text: string, chunkSize: number = 1000, overlap: number = 100): string[] {
    const chunks: string[] = [];
    let start = 0;
    
    while (start < text.length) {
        let end = start + chunkSize;
        
        // Intentar cortar en un punto natural (párrafo o frase)
        if (end < text.length) {
            const lastParagraph = text.lastIndexOf('\n\n', end);
            const lastPeriod = text.lastIndexOf('. ', end);
            
            if (lastParagraph > start + chunkSize / 2) {
                end = lastParagraph + 2;
            } else if (lastPeriod > start + chunkSize / 2) {
                end = lastPeriod + 2;
            }
        }
        
        const chunk = text.slice(start, end).trim();
        if (chunk.length > 50) {
            chunks.push(chunk);
        }
        
        start = end - overlap;
    }
    
    return chunks;
}

/**
 * Obtener estadísticas de la base de conocimiento
 */
export async function getKnowledgeStats(): Promise<{
    success: boolean;
    stats: { total_chunks: number; total_documents: number };
    error?: string;
}> {
    try {
        await connectToDatabase();
        
        const totalChunks = await KnowledgeModel.countDocuments();
        const uniqueTitles = await KnowledgeModel.distinct('title');
        
        return {
            success: true,
            stats: {
                total_chunks: totalChunks,
                total_documents: uniqueTitles.length,
            },
        };
    } catch (error) {
        console.error('Error getting knowledge stats:', error);
        return {
            success: false,
            stats: { total_chunks: 0, total_documents: 0 },
            error: String(error),
        };
    }
}

/**
 * Subir un documento a la base de conocimiento
 */
export async function uploadDocument(
    content: string,
    title?: string,
    metadata?: {
        source?: string;
        symbol?: string;
        tags?: string[];
        fileType?: string;
    }
): Promise<{
    success: boolean;
    document_id?: string;
    chunks_added?: number;
    error?: string;
}> {
    try {
        await connectToDatabase();
        
        // Dividir en chunks
        const chunks = chunkText(content);
        const docTitle = title || `Documento ${new Date().toISOString()}`;
        
        let chunksAdded = 0;
        let documentId = '';
        
        for (let i = 0; i < chunks.length; i++) {
            const chunk = chunks[i];
            
            // Generar embedding para este chunk
            const embedding = await generateEmbedding(chunk);
            
            // Crear preview
            const preview = chunk.substring(0, 200) + (chunk.length > 200 ? '...' : '');
            
            // Guardar en MongoDB
            const doc = await KnowledgeModel.create({
                title: docTitle,
                content: chunk,
                embedding,
                metadata: {
                    ...metadata,
                    chunkIndex: i,
                    totalChunks: chunks.length,
                },
                preview,
            });
            
            if (i === 0) {
                documentId = (doc._id as any).toString();
            }
            chunksAdded++;
        }
        
        return {
            success: true,
            document_id: documentId,
            chunks_added: chunksAdded,
        };
    } catch (error) {
        console.error('Error uploading document:', error);
        return {
            success: false,
            error: String(error),
        };
    }
}

/**
 * Búsqueda semántica en la base de conocimiento
 */
export async function searchKnowledge(
    query: string,
    nResults: number = 5
): Promise<{
    success: boolean;
    results: Array<{
        content: string;
        title: string;
        score: number;
        metadata: Record<string, any>;
    }>;
    count: number;
}> {
    try {
        await connectToDatabase();
        
        // Generar embedding de la query
        const queryEmbedding = await generateEmbedding(query);
        
        // Búsqueda vectorial usando MongoDB Atlas Search
        // Si el índice vectorial no está configurado, usar búsqueda de texto
        let results: any[] = [];
        
        try {
            // Intentar búsqueda vectorial
            results = await KnowledgeModel.aggregate([
                {
                    $vectorSearch: {
                        index: 'vector_index',
                        path: 'embedding',
                        queryVector: queryEmbedding,
                        numCandidates: nResults * 10,
                        limit: nResults,
                    },
                },
                {
                    $project: {
                        content: 1,
                        title: 1,
                        metadata: 1,
                        preview: 1,
                        score: { $meta: 'vectorSearchScore' },
                    },
                },
            ]);
        } catch (vectorError) {
            console.log('Vector search not available, falling back to text search');
            
            // Fallback: búsqueda de texto tradicional
            const textResults = await KnowledgeModel.find(
                { $text: { $search: query } },
                { score: { $meta: 'textScore' } }
            )
                .sort({ score: { $meta: 'textScore' } })
                .limit(nResults)
                .lean();
            
            // Normalizar scores para texto
            results = textResults.map((r) => ({
                content: r.content,
                title: r.title,
                metadata: r.metadata,
                preview: r.preview,
                score: Math.min((r as any).score / 10, 1), // Normalizar entre 0-1
            }));
        }
        
        return {
            success: true,
            results: results.map((r: any) => ({
                content: r.content,
                title: r.title,
                score: r.score || 0.5,
                metadata: r.metadata || {},
            })),
            count: results.length,
        };
    } catch (error) {
        console.error('Error searching knowledge:', error);
        return {
            success: false,
            results: [],
            count: 0,
        };
    }
}

/**
 * Obtener contexto RAG para análisis de acciones
 */
export async function getRAGContext(
    symbol: string,
    companyName: string
): Promise<{
    success: boolean;
    context: string;
}> {
    try {
        await connectToDatabase();
        
        // Buscar conocimiento relevante para este símbolo y empresa
        const queries = [
            `${symbol} ${companyName} análisis`,
            'criterios value investing',
            'análisis fundamental acciones',
        ];
        
        let allResults: string[] = [];
        
        for (const query of queries) {
            const searchResult = await searchKnowledge(query, 3);
            if (searchResult.success) {
                allResults.push(
                    ...searchResult.results
                        .filter(r => r.score > 0.3)
                        .map(r => r.content)
                );
            }
        }
        
        // También buscar documentos específicos del símbolo
        const symbolDocs = await KnowledgeModel.find({
            'metadata.symbol': symbol.toUpperCase(),
        })
            .limit(5)
            .lean();
        
        allResults.push(...symbolDocs.map((d: any) => d.content));
        
        // Eliminar duplicados y limitar contexto
        const uniqueResults = [...new Set(allResults)];
        const context = uniqueResults.slice(0, 10).join('\n\n---\n\n');
        
        return {
            success: true,
            context: context || 'No hay conocimiento específico disponible para esta acción.',
        };
    } catch (error) {
        console.error('Error getting RAG context:', error);
        return {
            success: false,
            context: '',
        };
    }
}

/**
 * Listar todos los documentos
 */
export async function listDocuments(
    limit: number = 50
): Promise<{
    success: boolean;
    documents: Array<{
        id: string;
        title: string;
        added_at: string;
        chunks: number;
        preview: string;
        metadata?: Record<string, any>;
    }>;
}> {
    try {
        await connectToDatabase();
        
        // Agrupar por título para mostrar documentos únicos
        const docs = await KnowledgeModel.aggregate([
            {
                $group: {
                    _id: '$title',
                    firstId: { $first: '$_id' },
                    createdAt: { $first: '$createdAt' },
                    preview: { $first: '$preview' },
                    chunks: { $sum: 1 },
                    metadata: { $first: '$metadata' },
                },
            },
            { $sort: { createdAt: -1 } },
            { $limit: limit },
        ]);
        
        return {
            success: true,
            documents: docs.map((d: any) => ({
                id: d.firstId.toString(),
                title: d._id,
                added_at: d.createdAt?.toISOString() || new Date().toISOString(),
                chunks: d.chunks,
                preview: d.preview,
                metadata: d.metadata,
            })),
        };
    } catch (error) {
        console.error('Error listing documents:', error);
        return {
            success: false,
            documents: [],
        };
    }
}

/**
 * Eliminar un documento (todos sus chunks)
 */
export async function deleteDocument(
    title: string
): Promise<{ success: boolean; deleted?: number }> {
    try {
        await connectToDatabase();
        
        const result = await KnowledgeModel.deleteMany({ title });
        
        return {
            success: true,
            deleted: result.deletedCount,
        };
    } catch (error) {
        console.error('Error deleting document:', error);
        return { success: false };
    }
}

/**
 * Obtener todo el contenido de la base de conocimiento
 */
export async function getAllKnowledgeContent(): Promise<{
    success: boolean;
    content: string;
}> {
    try {
        await connectToDatabase();
        
        const docs = await KnowledgeModel.find({})
            .sort({ title: 1, 'metadata.chunkIndex': 1 })
            .limit(100)
            .lean();
        
        const content = docs
            .map((d: any) => `📄 ${d.title}\n${d.content}`)
            .join('\n\n---\n\n');
        
        return {
            success: true,
            content: content || 'La base de conocimiento está vacía.',
        };
    } catch (error) {
        console.error('Error getting all content:', error);
        return {
            success: false,
            content: 'Error al cargar el contenido.',
        };
    }
}

/**
 * Subir archivo (procesa el contenido y lo guarda)
 */
export async function uploadFile(
    content: string,
    filename: string,
    fileType: string
): Promise<{
    success: boolean;
    document_id?: string;
    chunks_added?: number;
    error?: string;
}> {
    return uploadDocument(content, filename, {
        source: 'file_upload',
        fileType,
    });
}
