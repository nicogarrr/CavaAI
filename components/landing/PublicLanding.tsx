import Image from 'next/image';
import Link from 'next/link';
import type { Metadata } from 'next';
import { ArrowRight } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { SUPPORT_EMAIL } from '@/lib/config/brand';
import { isPublicSignUpOpen } from '@/lib/config/product';

/**
 * Metadatos de la landing.
 *
 * Viven aquí y la página los reexporta: `app/(public)/page.tsx` es
 * `export { default, metadata } from '@/components/landing/PublicLanding'`.
 * El título no incluye la marca porque la plantilla de `app/layout.tsx` ya
 * añade «| CavaAI».
 */
export const metadata: Metadata = {
    title: 'Research OS de inversión fundamental con fuentes trazables',
    description:
        'CavaAI convierte el research de una empresa en tesis trazables y versionadas: cada afirmación conserva su fuente y cada resultado revisa tu previsión.',
    alternates: { canonical: '/' },
    openGraph: {
        type: 'website',
        locale: 'es_ES',
        siteName: 'CavaAI',
        title: 'CavaAI: research de empresas con fuentes trazables y tesis versionadas',
        description:
            'Cada afirmación conserva su fuente, cada tesis tiene versión y cada resultado contrasta tu previsión. Metodología y términos públicos.',
    },
};

export default function PublicLanding() {
    const signUpOpen = isPublicSignUpOpen();
    const waitlistHref = `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent('Lista de espera de CavaAI')}`;

    return (
        <main id="content" tabIndex={-1} className="w-full overflow-x-clip">
            <section className="container pb-20 pt-12 text-center sm:pb-28 sm:pt-20">
                <p className="inline-flex items-center gap-2 rounded-full border border-teal-300/30 bg-teal-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-teal-300">
                    Research OS de inversión fundamental
                </p>
                <h1 className="mx-auto mt-6 max-w-3xl text-balance text-4xl font-bold leading-[1.1] tracking-tight text-gray-100 sm:text-6xl">
                    Tesis <span className="text-teal-300">trazables</span> que se revisan contra la
                    realidad
                </h1>
                <p className="mx-auto mt-6 max-w-2xl text-balance text-lg leading-8 text-gray-400">
                    Cada afirmación conserva su documento y su fecha, y cada tesis tiene versión. Si un
                    dato no está, CavaAI lo dice en lugar de inventarlo.
                </p>
                <div className="mt-9 flex flex-col items-stretch gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-center">
                    {signUpOpen ? (
                        <Button asChild size="lg">
                            <Link href="/sign-up">
                                Empezar mi primera tesis
                                <ArrowRight aria-hidden="true" />
                            </Link>
                        </Button>
                    ) : (
                        <Button asChild size="lg">
                            <a href={waitlistHref}>
                                Pedir acceso en la lista de espera
                                <ArrowRight aria-hidden="true" />
                            </a>
                        </Button>
                    )}
                    <Button asChild size="lg" variant="outline">
                        <Link href="/metodologia">Ver la metodología</Link>
                    </Button>
                </div>

                {/* Mockups: capturas reales de la app (fixture E2E etiquetado
                    como "Fuente de ejemplo" dentro de la propia interfaz). */}
                <div className="relative mx-auto mt-14 max-w-5xl sm:mt-16">
                    <div
                        aria-hidden="true"
                        className="pointer-events-none absolute -inset-x-16 -inset-y-16 -z-10 bg-[radial-gradient(ellipse_closest-side_at_50%_45%,rgba(45,212,191,0.14),transparent)]"
                    />
                    <figure className="overflow-hidden rounded-xl border border-gray-700/60 bg-surface-1 shadow-2xl shadow-black/50">
                        <div
                            aria-hidden="true"
                            className="flex items-center gap-1.5 border-b border-gray-700/60 bg-surface-overlay px-4 py-2.5"
                        >
                            <span className="h-2.5 w-2.5 rounded-full bg-gray-600" />
                            <span className="h-2.5 w-2.5 rounded-full bg-gray-600" />
                            <span className="h-2.5 w-2.5 rounded-full bg-gray-600" />
                        </div>
                        <div className="relative aspect-[16/9]">
                            <div className="absolute inset-x-0 -top-16 h-[calc(100%+4rem)]"><Image fill className="object-cover object-top"
                                src="/landing/ficha-pc.png"
                                alt="Ficha de empresa de CavaAI: precio con su fuente, variación y gráfico de evolución"
                               
                                priority
                                sizes="(min-width: 1024px) 1024px, 100vw"
                            /></div>
                        </div>
                    </figure>
                    {/* iPad dibujado en CSS (obra propia, sin assets de terceros):
                        canto de aluminio, bisel negro uniforme, botones laterales,
                        cámara frontal y reflejo de cristal. */}
                    <figure className="absolute -bottom-10 left-1/2 hidden w-[17rem] -translate-x-[118%] lg:block">
                        <span
                            aria-hidden="true"
                            className="absolute -right-[2px] top-14 h-8 w-[2px] rounded-r-sm bg-gradient-to-b from-zinc-400 to-zinc-600"
                        />
                        <span
                            aria-hidden="true"
                            className="absolute -right-[2px] top-[6.5rem] h-8 w-[2px] rounded-r-sm bg-gradient-to-b from-zinc-400 to-zinc-600"
                        />
                        <span
                            aria-hidden="true"
                            className="absolute -top-[2px] right-16 h-[2px] w-9 rounded-t-sm bg-gradient-to-r from-zinc-400 to-zinc-600"
                        />
                        <div className="rounded-[1.5rem] bg-gradient-to-br from-zinc-300 via-zinc-500 to-zinc-400 p-[2.5px] shadow-2xl shadow-black/80">
                            <div className="relative rounded-[1.4rem] bg-black p-[11px]">
                                <div
                                    aria-hidden="true"
                                    className="absolute left-1/2 top-[3.5px] z-20 h-[5px] w-[5px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_35%_35%,#4b5563,#05070b_70%)] ring-1 ring-zinc-800"
                                />
                                <div className="relative aspect-[3/4] overflow-hidden rounded-[0.8rem] bg-surface-1">
                                    <Image fill className="object-cover object-top"
                                        src="/landing/ficha-tablet.png"
                                        alt="CavaAI en tablet: la misma ficha adaptada a pantalla mediana"
                                        sizes="272px"
                                    />
                                    <div
                                        aria-hidden="true"
                                        className="pointer-events-none absolute inset-0 bg-[linear-gradient(115deg,rgba(255,255,255,0.07)_0%,rgba(255,255,255,0)_38%)]"
                                    />
                                </div>
                            </div>
                        </div>
                    </figure>
                    <figure className="absolute -bottom-8 right-3 w-28 overflow-hidden rounded-[1.75rem] border-2 border-gray-600/80 bg-surface-1 shadow-2xl shadow-black/60 sm:-bottom-10 sm:right-6 sm:w-40">
                        <div
                            aria-hidden="true"
                            className="absolute left-1/2 top-1.5 z-10 h-1.5 w-10 -translate-x-1/2 rounded-full bg-gray-600"
                        />
                        <div className="relative aspect-[390/760]">
                            <div className="absolute inset-x-0 -top-16 h-[calc(100%+4rem)]"><Image fill className="object-cover object-top"
                                src="/landing/ficha-movil.png"
                                alt="CavaAI en móvil: precio y gráfico de la ficha de empresa"
                                sizes="(min-width: 640px) 160px, 128px"
                            /></div>
                        </div>
                    </figure>
                </div>
                <p className="mx-auto mt-16 max-w-xl text-xs text-gray-500">
                    Capturas reales de la aplicación con datos de ejemplo. La interfaz declara de dónde
                    sale cada cifra que muestra, o que no hay fuente disponible.
                </p>
            </section>
        </main>
    );
}
