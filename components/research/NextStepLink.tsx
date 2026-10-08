'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';

/**
 * Enlace de "Por dónde seguir": navega a otra vista de la misma ficha y lleva
 * la pantalla al inicio. En móvil el botón está al final de una página larga y,
 * sin esto, la vista nueva se abre con el scroll abajo y parece que no ocurre
 * nada.
 */
export function NextStepLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      className="flex min-h-[44px] items-center rounded-lg border border-gray-800 p-3 text-sm text-gray-200 transition hover:border-teal-700 hover:text-teal-200"
      href={href}
      onClick={() => {
        window.scrollTo({ top: 0, behavior: 'auto' });
      }}
      scroll
    >
      {children}
    </Link>
  );
}
