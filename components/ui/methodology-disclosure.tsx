import { ChevronDown, CircleHelp } from 'lucide-react';
import type { ReactNode } from 'react';

/**
 * Muro de metodología colapsado (quick win UX 2): la página abre con el
 * contenido y la explicación queda a un toque. <details> nativo: funciona
 * sin JS de cliente y cerrado por defecto en TODOS los viewports (al
 * contrario que CollapsiblePanel, pensado para lo contrario).
 */
export function MethodologyDisclosure({
    title = 'Metodología y límites',
    children,
}: {
    title?: string;
    children: ReactNode;
}) {
    return (
        <details className="group rounded-xl border border-gray-800 bg-[#101010] px-4 py-1">
            <summary className="flex min-h-[44px] cursor-pointer list-none items-center gap-2 text-sm font-medium text-gray-300 [&::-webkit-details-marker]:hidden">
                <CircleHelp aria-hidden="true" className="h-4 w-4 shrink-0 text-teal-300" />
                {title}
                <ChevronDown aria-hidden="true" className="ml-auto h-4 w-4 shrink-0 text-gray-500 transition-transform group-open:rotate-180" />
            </summary>
            <div className="space-y-2 pb-3 text-sm leading-6 text-gray-500">{children}</div>
        </details>
    );
}
