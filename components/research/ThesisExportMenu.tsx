"use client";

import { FileDown } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/**
 * Las 4 salidas de la tesis (journal, memo, EPUB, Obsidian) recogidas en un
 * unico menu. Antes eran 4 botones sueltos en la barra de la vista Tesis y
 * comian el foco de las acciones primarias (generar/aprobar). Las rutas no
 * cambian: mismos endpoints, misma descarga.
 */
export default function ThesisExportMenu({ ticker }: { ticker: string }) {
  const encoded = encodeURIComponent(ticker);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="inline-flex min-h-[44px] items-center gap-2 rounded-md border border-gray-700 px-4 py-2 text-sm font-medium text-gray-200 transition hover:border-teal-700 hover:text-teal-200 sm:min-h-0">
        <FileDown className="h-4 w-4" />
        Exportar
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <DropdownMenuItem asChild className="min-h-[44px] sm:min-h-0">
          <a href="/export">Journal (.zip)</a>
        </DropdownMenuItem>
        <DropdownMenuItem asChild className="min-h-[44px] sm:min-h-0">
          <a href={`/api/thesis-memo/${encoded}`}>Memo de la tesis</a>
        </DropdownMenuItem>
        <DropdownMenuItem asChild className="min-h-[44px] sm:min-h-0">
          <a href={`/api/thesis/${encoded}/epub`} download>
            EPUB
          </a>
        </DropdownMenuItem>
        <DropdownMenuItem asChild className="min-h-[44px] sm:min-h-0">
          <a href={`/api/thesis/${encoded}/obsidian.zip`} download>
            Obsidian (.zip)
          </a>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
