import { BookDown } from 'lucide-react';

/**
 * Descarga de la tesis vigente en EPUB.
 *
 * Ruta proxy same-origin (el navegador no puede firmar la
 * identidad del data-engine): /api/thesis/[ticker]/epub sirve o
 * construye el EPUB. No existe backend PDF: no ofrecerlo.
 */
export default function ThesisExportButtons({ ticker }: { ticker: string }) {
  const encoded = encodeURIComponent(ticker);
  return (
    <a
      className="inline-flex min-h-[44px] items-center gap-2 rounded-md border border-gray-700 px-4 py-2 text-sm font-medium text-gray-200 transition hover:border-teal-700 hover:text-teal-200 sm:min-h-0"
      href={`/api/thesis/${encoded}/epub`}
      download
    >
      <BookDown className="h-4 w-4" />
      Exportar EPUB
    </a>
  );
}
