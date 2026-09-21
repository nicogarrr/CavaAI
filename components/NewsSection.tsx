import { getNews } from '@/lib/actions/finnhub.actions';
import Image from 'next/image';

interface NewsSectionProps {
    symbols?: string[];
}

export default async function NewsSection({ symbols }: NewsSectionProps) {
    let news;
    try {
        news = await getNews(symbols);
    } catch (error) {
        console.error('Error loading news:', error);
        return (
            <div className="w-full h-full bg-[#0F0F0F] rounded-lg border border-gray-800 p-6 flex items-center justify-center">
                <p className="text-gray-500">Error al cargar las noticias. Por favor, intenta más tarde.</p>
            </div>
        );
    }

    return (
            <div className="w-full min-w-0 h-full bg-[#0F0F0F] rounded-lg border border-gray-800 p-4 sm:p-6 overflow-y-auto">
                <h2 className="text-xl sm:text-2xl font-bold text-white mb-4 sm:mb-6 break-words">Noticias destacadas</h2>

                {news.length === 0 ? (
                    <div className="flex items-center justify-center px-4 py-12 text-center text-sm text-gray-500">
                        <p>No hay noticias disponibles en este momento.</p>
                    </div>
                ) : (
                    <div className="space-y-3 sm:space-y-4">
                        {news.map((article, index) => (
                            <a
                                key={`${article.id}-${index}`}
                                href={article.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="block min-w-0 p-4 bg-[#141414] hover:bg-[#1a1a1a] rounded-lg border border-gray-800 transition-all duration-200 group"
                            >
                                <div className="flex flex-col min-[420px]:flex-row gap-3 sm:gap-4">
                                    {article.image && (
                                        <div className="h-40 w-full min-w-0 shrink-0 relative rounded-lg overflow-hidden min-[420px]:h-24 min-[420px]:w-32">
                                            <Image
                                                src={article.image}
                                                alt={article.headline}
                                                fill
                                                className="object-cover"
                                                unoptimized
                                            />
                                        </div>
                                    )}
                                    <div className="flex-1 min-w-0">
                                        <h3 className="text-white text-sm sm:text-base font-semibold mb-2 line-clamp-2 group-hover:text-[#0FEDBE] transition-colors break-words">
                                            {article.headline}
                                        </h3>
                                        <p className="text-gray-400 text-sm mb-2 line-clamp-2 break-words">
                                            {article.summary}
                                        </p>
                                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
                                            {article.source && (
                                                <span className="font-medium text-[#0FEDBE]">
                                                    {article.source}
                                                </span>
                                            )}
                                            {article.datetime && (
                                                <span>
                                                    {new Date(article.datetime * 1000).toLocaleDateString('es-ES', {
                                                        day: 'numeric',
                                                        month: 'short',
                                                        year: 'numeric',
                                                        hour: '2-digit',
                                                        minute: '2-digit',
                                                    })}
                                                </span>
                                            )}
                                            {article.related && (
                                                <span className="px-2 py-0.5 bg-[#0FEDBE]/10 text-[#0FEDBE] rounded">
                                                    {article.related}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </a>
                        ))}
                    </div>
                )}
            </div>
    );
}

