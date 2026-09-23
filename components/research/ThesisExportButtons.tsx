import { BookDown, FileDown } from 'lucide-react';

/**
 * Descargas de la tesis vigente en PDF y EPUB.
 *
 * Ambas rutas son proxies same-origin (el navegador no puede firmar la
 * identidad del data-engine): /api/thesis/[ticker]/pdf genera el PDF en el
 * servidor y /api/thesis/[ticker]/epub sirve o construye el EPUB.
 */
export default function ThesisExportButtons({ ticker }: { ticker: string }) {
  const encoded = encodeURIComponent(ticker);
  return (
    <>
      <a
        className="inline-flex min-h-[44px] items-center gap-2 rounded-md border border-gray-700 px-4 py-2 text-sm font-medium text-gray-200 transition hover:border-teal-700 hover:text-teal-200 sm:min-h-0"
        href={`/api/thesis/${encoded}/pdf`}
        download
      >
        <FileDown className="h-4 w-4" />
        Exportar PDF
      </a>
      <a
        className="inline-flex min-h-[44px] items-center gap-2 rounded-md border border-gray-700 px-4 py-2 text-sm font-medium text-gray-200 transition hover:border-teal-700 hover:text-teal-200 sm:min-h-0"
        href={`/api/thesis/${encoded}/epub`}
        download
      >
        <BookDown className="h-4 w-4" />
        Exportar EPUB
      </a>
    </>
  );
}
