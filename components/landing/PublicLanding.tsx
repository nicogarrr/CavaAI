import Image from 'next/image';
import Link from 'next/link';
import type { Metadata } from 'next';
import { ArrowRight } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { isPublicSignUpOpen } from '@/lib/config/product';

/**
 * Metadatos de la landing.
 *
 * Viven aquí y la página los reexporta: `app/(public)/page.tsx` es
 * `export { default, metadata } from '@/components/landing/PublicLanding'`.
 * El título no incluye la marca porque la plantilla de `app/layout.tsx` ya
 * añade «| GerarAI».
 */
export const metadata: Metadata = {
    title: 'Research OS de inversión fundamental con fuentes trazables',
    description:
        'GerarAI convierte el research de una empresa en tesis trazables y versionadas: cada afirmación conserva su fuente y cada resultado revisa tu previsión.',
    alternates: { canonical: '/' },
    openGraph: {
        type: 'website',
        locale: 'es_ES',
        siteName: 'GerarAI',
        title: 'GerarAI: research de empresas con fuentes trazables y tesis versionadas',
        description:
            'Cada afirmación conserva su fuente, cada tesis tiene versión y cada resultado contrasta tu previsión. Metodología pública.',
    },
};

export default function PublicLanding() {
    const signUpOpen = isPublicSignUpOpen();

    return (
        <main id="content" tabIndex={-1} className="w-full overflow-x-clip">
            <section className="container pb-16 pt-10 text-left sm:pb-28 sm:pt-20 sm:text-center">
                <p className="inline-flex max-w-full items-center text-[10px] font-semibold uppercase leading-5 tracking-[0.16em] text-teal-300 sm:text-xs sm:tracking-[0.2em]">
                    Research OS de inversión fundamental
                </p>
                <h1 style={{ fontFamily: "var(--font-editorial), Georgia, serif" }} className="mx-auto mt-4 max-w-3xl text-balance text-[clamp(2.7rem,11vw,3.1rem)] font-normal leading-[1.12] tracking-[-0.015em] text-gray-100 sm:mt-6 sm:text-7xl">
                    Tesis <span className="text-teal-300">trazables</span> que se revisan contra la
                    realidad
                </h1>
                <p className="mx-auto mt-5 max-w-2xl text-base leading-7 text-gray-400 sm:mt-6 sm:text-balance sm:text-lg sm:leading-8">
                    Cada afirmación conserva su documento y su fecha, y cada tesis tiene versión. Si un
                    dato no está, GerarAI lo dice en lugar de inventarlo.
                </p>
                <div className="mt-7 flex flex-col items-stretch gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-center">
                    {signUpOpen ? (
                        <Button asChild size="lg">
                            <Link href="/sign-up">
                                Empezar mi primera tesis
                                <ArrowRight aria-hidden="true" />
                            </Link>
                        </Button>
                    ) : (
                        <Button asChild size="lg">
                            <Link href="/sign-up">
                                Pedir acceso
                                <ArrowRight aria-hidden="true" />
                            </Link>
                        </Button>
                    )}
                    <Button asChild size="lg" variant="outline">
                        <Link href="/metodologia">Ver la metodología</Link>
                    </Button>
                </div>

                {/* Mockups: capturas reales de la app (fixture E2E etiquetado
                    como "Fuente de ejemplo" dentro de la propia interfaz). */}
                <div className="relative mx-auto mt-12 max-w-5xl sm:mt-16">
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
                                alt="Ficha de empresa de GerarAI: precio con su fuente, variación y gráfico de evolución"
                               
                                priority
                                sizes="(min-width: 1024px) 1024px, 100vw"
                            /></div>
                        </div>
                    </figure>
                    {/* iPad horizontal dibujado en CSS (obra propia, sin assets de terceros):
                        marco fino de aluminio, bisel negro uniforme y captura 4:3 completa. */}
                    <figure className="absolute -bottom-10 left-1/2 hidden w-[22rem] -translate-x-[100%] lg:block">
                        <div className="rounded-[1.4rem] bg-gradient-to-br from-zinc-300 via-zinc-500 to-zinc-400 p-[2px] shadow-2xl shadow-black/80">
                            <div className="relative rounded-[1.3rem] bg-black p-[10px]">
                                <div
                                    aria-hidden="true"
                                    className="absolute left-[4px] top-1/2 z-20 h-[4px] w-[4px] -translate-y-1/2 rounded-full bg-zinc-700"
                                />
                                <div className="relative aspect-[4/3] overflow-hidden rounded-[0.7rem] bg-surface-1">
                                    <Image fill className="object-cover"
                                        src="/landing/ficha-tablet.png"
                                        alt="GerarAI en tablet: la misma ficha adaptada a pantalla mediana"
                                        sizes="352px"
                                    />
                                    <div
                                        aria-hidden="true"
                                        className="pointer-events-none absolute inset-0 bg-[linear-gradient(115deg,rgba(255,255,255,0.07)_0%,rgba(255,255,255,0)_38%)]"
                                    />
                                </div>
                            </div>
                        </div>
                    </figure>
                    {/* iPhone dibujado en CSS (obra propia): marco fino, isla dinámica y
                        captura completa 390:844 sin recortar, con margen uniforme. */}
                    <figure className="absolute -bottom-8 right-3 w-28 sm:-bottom-10 sm:right-6 sm:w-40">
                        <div className="rounded-[1.9rem] bg-gradient-to-br from-zinc-300 via-zinc-500 to-zinc-400 p-[1.5px] shadow-2xl shadow-black/60 sm:rounded-[2.4rem]">
                            <div className="relative rounded-[1.8rem] bg-black p-[4px] sm:rounded-[2.3rem] sm:p-[5px]">
                                <div className="relative aspect-[390/903] overflow-hidden rounded-[1.5rem] bg-black sm:rounded-[2rem]">
                                    {/* Barra de estado tipo iOS: la isla vive aquí y la app empieza debajo. */}
                                    <div
                                        aria-hidden="true"
                                        className="absolute inset-x-0 top-0 z-10 flex h-[6.5%] items-center justify-between px-[9%] text-[5px] font-semibold leading-none text-white sm:text-[7px]"
                                    >
                                        <span>9:41</span>
                                        <span className="flex items-center gap-[2px]">
                                            <span className="flex items-end gap-[1px]">
                                                <i className="block h-[2px] w-[1.5px] bg-white" />
                                                <i className="block h-[3px] w-[1.5px] bg-white" />
                                                <i className="block h-[4px] w-[1.5px] bg-white" />
                                            </span>
                                            <span className="block h-[4px] w-[8px] rounded-[1.5px] border border-white/70 p-[0.5px] sm:h-[5px] sm:w-[11px]">
                                                <i className="block h-full w-[75%] rounded-[0.5px] bg-white" />
                                            </span>
                                        </span>
                                    </div>
                                    <div
                                        aria-hidden="true"
                                        className="absolute left-1/2 top-[1.3%] z-20 h-[4.1%] w-[30%] -translate-x-1/2 rounded-full bg-black ring-1 ring-zinc-800"
                                    />
                                    <div className="absolute inset-x-0 bottom-0 aspect-[390/844]">
                                        <Image fill className="object-cover"
                                            src="/landing/ficha-movil.png"
                                            alt="GerarAI en móvil: precio y gráfico de la ficha de empresa"
                                            sizes="(min-width: 640px) 160px, 112px"
                                        />
                                    </div>
                                </div>
                            </div>
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
