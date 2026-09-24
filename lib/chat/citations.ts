/**
 * Citas trazables del chat: del backend (sources) al frontend con
 * localizador estable. Módulo puro (sin 'use server'): las server actions
 * no pueden exportar funciones síncronas.
 */

export interface ChatSource {
    type: string;
    id: number | string | null;
    title: string;
    document_id?: number | null;
    document_chunk_id?: number | null;
    page_number?: number | null;
    chunk_index?: number | null;
    source_type?: string | null;
    [key: string]: unknown;
}

/** Cita trazable: del backend (sources) al frontend con localizador estable. */
export interface ChatCitation {
    chunk_id: number | string | null;
    document: string;
    page: number | null;
    locator: string;
    source_type: string | null;
}

/** Deriva citations[{chunk_id,document,page,locator}] de los sources del backend. */
export function toChatCitations(
    sources: ChatSource[] | undefined | null,
): ChatCitation[] {
    if (!sources) return [];
    const citations: ChatCitation[] = [];
    for (const source of sources) {
        const kind = source.type;
        if (kind === 'document_chunk' || kind === 'rag_chunk' || kind === 'claim_evidence') {
            const chunkId =
                kind === 'claim_evidence'
                    ? (source.document_chunk_id as number | null | undefined) ?? null
                    : source.id;
            const document =
                typeof source.title === 'string' && source.title
                    ? source.title
                    : `Documento ${String(source.document_id ?? '')}`.trim() || 'Documento';
            const page =
                typeof source.page_number === 'number' ? source.page_number : null;
            const locator =
                kind === 'claim_evidence'
                    ? `claim_evidence:${String(source.id)}`
                    : `${kind}:${String(source.id)}`;
            citations.push({
                chunk_id: chunkId,
                document,
                page,
                locator,
                source_type:
                    typeof source.source_type === 'string' ? source.source_type : null,
            });
        }
    }
    return citations;
}
