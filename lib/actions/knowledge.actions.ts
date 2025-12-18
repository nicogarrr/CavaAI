'use server';

const KB_API_URL = 'http://127.0.0.1:8000';

/**
 * Get knowledge base statistics
 */
export async function getKnowledgeStats(): Promise<{
    success: boolean;
    stats: Record<string, number>;
    collections: string[];
}> {
    try {
        const res = await fetch(`${KB_API_URL}/knowledge/stats`, {
            cache: 'no-store',
        });
        if (!res.ok) throw new Error('Failed to fetch stats');
        return await res.json();
    } catch (error) {
        console.error('Error fetching knowledge stats:', error);
        return { success: false, stats: {}, collections: [] };
    }
}

/**
 * Upload a document to the knowledge base
 */
export async function uploadDocument(
    collection: string,
    content: string,
    title?: string,
    symbol?: string,
    tags?: string[]
): Promise<{
    success: boolean;
    document_id?: string;
    chunks_added?: number;
    error?: string;
}> {
    try {
        const res = await fetch(`${KB_API_URL}/knowledge/upload`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ collection, content, title, symbol, tags }),
        });

        if (!res.ok) {
            const error = await res.text();
            return { success: false, error };
        }

        return await res.json();
    } catch (error) {
        console.error('Error uploading document:', error);
        return { success: false, error: String(error) };
    }
}

/**
 * Search the knowledge base
 */
export async function searchKnowledge(
    query: string,
    collections?: string[],
    nResults: number = 5
): Promise<{
    success: boolean;
    results: Array<{
        content: string;
        collection: string;
        score: number;
        metadata: Record<string, any>;
    }>;
    count: number;
}> {
    try {
        const res = await fetch(`${KB_API_URL}/knowledge/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, collections, n_results: nResults }),
        });

        if (!res.ok) throw new Error('Search failed');
        return await res.json();
    } catch (error) {
        console.error('Error searching knowledge:', error);
        return { success: false, results: [], count: 0 };
    }
}

/**
 * Get context for stock analysis (used by AI)
 */
export async function getAnalysisContext(
    symbol: string,
    companyName: string
): Promise<{
    success: boolean;
    context: string;
}> {
    try {
        const res = await fetch(`${KB_API_URL}/knowledge/context`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol, company_name: companyName }),
        });

        if (!res.ok) throw new Error('Context fetch failed');
        return await res.json();
    } catch (error) {
        console.error('Error getting analysis context:', error);
        return { success: false, context: '' };
    }
}

/**
 * List documents in a collection
 */
export async function listDocuments(
    collection: string,
    limit: number = 50
): Promise<{
    success: boolean;
    documents: Array<{
        id: string;
        title: string;
        added_at: string;
        chunks: number;
        preview: string;
    }>;
}> {
    try {
        const res = await fetch(`${KB_API_URL}/knowledge/list/${collection}?limit=${limit}`, {
            cache: 'no-store',
        });
        if (!res.ok) throw new Error('List failed');
        return await res.json();
    } catch (error) {
        console.error('Error listing documents:', error);
        return { success: false, documents: [] };
    }
}

/**
 * Delete a document
 */
export async function deleteDocument(
    collection: string,
    documentId: string
): Promise<{ success: boolean }> {
    try {
        const res = await fetch(`${KB_API_URL}/knowledge/delete/${collection}/${documentId}`, {
            method: 'DELETE',
        });
        return await res.json();
    } catch (error) {
        console.error('Error deleting document:', error);
        return { success: false };
    }
}
