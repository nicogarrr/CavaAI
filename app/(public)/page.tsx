import type { Metadata } from 'next';

import PublicLanding, { metadata as landingMetadata } from '@/components/landing/PublicLanding';

/**
 * Landing publica en `/`.
 *
 * El dashboard autenticado vive en `/inicio` (`app/(root)/inicio/page.tsx`): el
 * App Router no admite dos paginas en la misma ruta, y `/` es la direccion que
 * un visitante desconocido teclea o recibe de un enlace. El cambio de URL es
 * invisible para el usuario con sesion porque el layout publico y el wordmark
 * de la app lo llevan ahi, y `/inicio` es la unica ruta de la app que el menu
 * declara como Inicio.
 */
export const metadata: Metadata = landingMetadata;

export default function LandingPage() {
    return <PublicLanding />;
}
