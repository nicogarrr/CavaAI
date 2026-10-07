'use client';

import Link from 'next/link';
import { useState } from 'react';

import { askKnowledge, type LibraryAnswer } from '@/lib/actions/knowledge-chat.actions';

export function LibraryChat({ scope = 'letters', authors = [] }: { scope?: 'letters' | 'library'; authors?: string[] }) {
  const [question, setQuestion] = useState('');
  const [author, setAuthor] = useState('');
  const [result, setResult] = useState<LibraryAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError(null); setResult(null);
    try { setResult(await askKnowledge(question, scope, author)); }
    catch { setError('No se pudo consultar la biblioteca. Inténtalo de nuevo.'); }
    finally { setBusy(false); }
  }
  return <section aria-label="Preguntar a la biblioteca" className="flex min-w-0 flex-col gap-3 rounded-xl border border-gray-800 p-4">
    <h2 className="text-xl font-semibold">{scope === 'letters' ? 'Preguntar a las cartas' : 'Preguntar a la biblioteca'}</h2>
    <p className="text-xs text-amber-300">Doctrina, no datos actuales de empresas. Síntesis del modelo con citas; el original manda.</p>
    <form onSubmit={submit} className="flex flex-col gap-3">
      {authors.length > 0 && <label className="text-sm">Autor
        <select value={author} onChange={event => { setAuthor(event.target.value); setResult(null); }} className="mt-1 block w-full rounded-lg border border-gray-700 bg-surface-1 p-2">
          <option value="">Todos los autores</option>{authors.map(name => <option key={name} value={name}>{name}</option>)}
        </select>
      </label>}
      <label className="text-sm" htmlFor={`library-question-${scope}`}>Pregunta</label>
      <textarea id={`library-question-${scope}`} value={question} onChange={event => setQuestion(event.target.value)} required minLength={3} maxLength={1200} rows={2} placeholder="¿Qué dice Buffett sobre las recompras?" className="w-full rounded-lg border border-gray-700 bg-surface-1 p-3 text-sm" />
      <button disabled={busy || question.trim().length < 3} className="self-start rounded-lg bg-lime-300 px-4 py-2 text-sm font-medium text-gray-950 disabled:opacity-50">{busy ? 'Consultando…' : 'Preguntar'}</button>
    </form>
    <div aria-live="polite" className="flex flex-col gap-4">
      {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
      {result?.message && <p className="text-sm text-gray-400">{result.message}</p>}
      {result?.retrieval === 'solo_texto' && <p className="text-xs text-gray-500">Búsqueda por texto. Prueba también términos del idioma original.</p>}
      {result?.answers.map((answer, index) => {
        const cite = answer.citation;
        const reader = cite.document_type === 'fund_letter' ? `/inversores/cartas/${cite.document_id}?pagina=${Math.floor(cite.chunk_index / 8) + 1}#chunk-${cite.chunk_id}` : `/knowledge?document=${cite.document_id}`;
        const original = cite.source_url && /^https?:\/\//i.test(cite.source_url) ? `${cite.source_url}${cite.source_url.includes('#') || cite.page_number === null ? '' : `#page=${cite.page_number}`}` : null;
        return <article key={`${cite.chunk_id}-${index}`} className="min-w-0 border-t border-gray-800 pt-3">
          {answer.text && <p className="mb-2 whitespace-pre-wrap break-words text-sm">{answer.text}</p>}
          <blockquote className="whitespace-pre-wrap break-words border-l-2 border-lime-300 pl-3 text-sm leading-6 text-gray-300">{cite.quote}</blockquote>
          <p className="mt-2 text-xs text-gray-500">{cite.author ?? 'Autor no registrado'} · {cite.title} · {cite.page_number === null ? 'Página no registrada' : `Página ${cite.page_number}`} · Fragmento {cite.chunk_index + 1} · {cite.publication_date ?? 'Fecha no registrada'}</p>
          <div className="mt-2 flex flex-wrap gap-4 text-sm text-lime-300"><Link href={reader}>Ver fragmento</Link>{original && <a href={original} target="_blank" rel="noreferrer">Original</a>}</div>
        </article>;
      })}
    </div>
  </section>;
}
