'use server';

import { normalizeResearchBody, researchIdentityHeaders } from '@/lib/auth/research-identity';

export type LibraryAnswer = {
  status: 'ok' | 'fragmentos' | 'sin_datos';
  kind: 'doctrina';
  retrieval: string;
  message: string | null;
  answers: {
    text: string | null;
    citation: {
      chunk_id: number; document_id: number; title: string; author: string | null;
      page_number: number | null; chunk_index: number; quote: string;
      source_url: string | null; publication_date: string | null; document_type: string;
    };
  }[];
};

export async function askKnowledge(question: string, scope: 'letters' | 'library', author?: string): Promise<LibraryAnswer> {
  const trimmed = question.trim();
  if (trimmed.length < 3 || trimmed.length > 1200) throw new Error('Escribe una pregunta de 3 a 1200 caracteres.');
  const path = '/api/knowledge/chat';
  const normalized = await normalizeResearchBody(JSON.stringify({ question: trimmed, scope, author: author || null }));
  const identity = await researchIdentityHeaders({ method: 'POST', path, body: normalized.body ?? null });
  const response = await fetch(`${process.env.FMP_BACKEND_URL ?? 'http://localhost:8000'}${path}`, {
    method: 'POST', cache: 'no-store', body: normalized.body,
    headers: { ...identity, 'Content-Type': 'application/json' },
  });
  if (!response.ok) throw new Error('No se pudo consultar la biblioteca. Inténtalo de nuevo.');
  return response.json() as Promise<LibraryAnswer>;
}
