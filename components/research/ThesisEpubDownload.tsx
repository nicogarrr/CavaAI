import { BookDown } from 'lucide-react';

/**
 * Botón de descarga del EPUB de la tesis vigente + ayuda «Enviar a Kindle».
 * Apunta al proxy same-origin /api/thesis/[ticker]/epub (el navegador no
 * puede firmar la identidad del data-engine, la firma el servidor).
 */
export function ThesisEpubDownload({ ticker }: { ticker: string }) {
  const href = `/api/thesis/${encodeURIComponent(ticker)}/epub`;
  return (
    <div className="rounded-xl border border-gray-800 bg-[#101010] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-gray-100">Exportar tesis</h2>
          <p className="mt-1 text-sm text-gray-400">
            Descarga la tesis vigente en formato EPUB: portada, resumen, secciones,
            citas y aviso legal.
          </p>
        </div>
        <a
          href={href}
          download
          className="inline-flex items-center justify-center gap-2 rounded-md bg-teal-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-teal-500"
        >
          <BookDown className="h-4 w-4" />
          Descargar EPUB
        </a>
      </div>
      <p className="mt-4 text-xs leading-5 text-gray-500">
        Enviar a Kindle: descarga el archivo y envíalo como adjunto desde tu correo
        verificado a tu dirección @kindle.com (o súbelo en kindle.amazon.com con
        «Enviar a Kindle»). También puedes copiarlo por USB a la carpeta «documents»
        de tu Kindle.
      </p>
    </div>
  );
}
