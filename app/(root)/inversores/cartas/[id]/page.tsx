import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import BackendOffline from '@/components/system/BackendOffline';
import { getKnowledgeDocumentChunks, getKnowledgeDocuments } from '@/lib/actions/research-tools.actions';
import { isBackendUnavailableError } from '@/lib/backend-offline';

import { Pagination, paginate } from '../../_components/Pagination';
import { authorKey, titleYear } from '../letters';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export const metadata: Metadata = {
    title: 'Leer carta',
    description: 'Texto de una carta a inversores, por fragmentos, con enlace al PDF original.',
};

const PAGE_SIZE = 8;
const LINK = 'text-sm text-lime-300 hover:underline';

type PageProps = {
    params: Promise<{ id: string }>;
    searchParams: Promise<{ pagina?: string }>;
};

export default async function LetterReaderPage({ params, searchParams }: PageProps) {
    const { id } = await params;
    const { pagina } = await searchParams;
    const letterId = /^\d+$/.test(id) ? Number(id) : null;
    if (!letterId) notFound();

    let documents: Awaited<ReturnType<typeof getKnowledgeDocuments>>;
    let chunks: Awaited<ReturnType<typeof getKnowledgeDocumentChunks>>;
    try {
        [documents, chunks] = await Promise.all([getKnowledgeDocuments(), getKnowledgeDocumentChunks(letterId)]);
    } catch (error) {
        if (isBackendUnavailableError(error)) {
            return <BackendOffline feature="Carta" retryHref={`/inversores/cartas/${letterId}`} />;
        }
        throw error;
    }

    const letter = documents.find((doc) => doc.id === letterId && doc.document_type === 'fund_letter');
    if (!letter) notFound();

    const year = titleYear(letter.title);
    const author = letter.author?.trim() || null;
    const backHref = author ? `/inversores/cartas?autor=${authorKey(author) || 'sin-autor'}` : '/inversores/cartas?autor=sin-autor';
    const ordered = [...chunks].sort((a, b) => Number(a.chunk_index) - Number(b.chunk_index));
    const paged = paginate(ordered, pagina, PAGE_SIZE);

    return (
        <main id="content" tabIndex={-1} className="mx-auto flex w-full min-w-0 max-w-3xl flex-col gap-8 overflow-x-clip py-6">
            <header className="flex flex-col gap-3">
                <Link className={LINK} href={backHref}>
                    Volver a las cartas{author ? ` de ${author}` : ''}
                </Link>
                <h1 className="text-2xl font-semibold text-gray-100 sm:text-3xl">{letter.title}</h1>
                <p className="text-sm text-gray-400">
                    {author ?? 'Autor no registrado'}
                    {' · '}
                    {letter.publication_date
                        ? `Publicada el ${letter.publication_date}`
                        : `Fecha de publicación no registrada${year ? ` · el título indica ${year}` : ''}`}
                </p>
                {letter.source_url ? (
                    <a className={LINK} href={letter.source_url} rel="noreferrer" target="_blank">
                        Abrir el PDF original
                    </a>
                ) : (
                    <span className="text-xs text-gray-600">Sin PDF original</span>
                )}
            </header>

            {paged.items.length === 0 ? (
                <p className="text-sm text-gray-500">Esta carta no tiene texto extraído en la biblioteca. Abre el PDF original.</p>
            ) : (
                <section aria-label="Texto de la carta" className="flex flex-col gap-4">
                    {paged.items.map((chunk) => (
                        <article className="rounded-2xl border border-gray-800 bg-surface-1 p-4 sm:p-5" key={chunk.id}>
                            <p className="mb-2 text-xs text-gray-500">
                                Fragmento {Number(chunk.chunk_index) + 1}
                                {chunk.page_number === null || chunk.page_number === undefined ? '' : ` · página ${chunk.page_number}`}
                            </p>
                            <p className="whitespace-pre-wrap break-words text-sm leading-7 text-gray-300">{chunk.content}</p>
                        </article>
                    ))}
                </section>
            )}

            <Pagination basePath={`/inversores/cartas/${letterId}`} page={paged.page} total={paged.total} />

            <p className="text-xs text-gray-500">
                Fuente: biblioteca de CavaAI, texto extraído del PDF y troceado en fragmentos (puede tener errores de extracción;
                el PDF original manda). Es doctrina de inversión, no datos de las empresas.
            </p>
        </main>
    );
}
