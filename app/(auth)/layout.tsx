import Link from "next/link";
import React from "react";
import {headers} from "next/headers";
import {redirect} from "next/navigation";
import {getAuth} from "@/lib/better-auth/auth";
import {CavaAIWordmark} from "@/components/CavaAIWordmark";
import {LineChart, Star} from "lucide-react";
import {productChain, productModules} from "@/lib/config/product";

// Forzar renderizado dinámico porque usa headers() para verificar sesión
export const dynamic = 'force-dynamic';
export const revalidate = 0;

const Layout = async ({ children }: { children : React.ReactNode }) => {
    const browserTestBypass = process.env.E2E_AUTH_BYPASS === '1' && process.env.NODE_ENV !== 'production';
    if (!browserTestBypass) {
        const auth = await getAuth();
        const session = await auth.api.getSession({headers: await headers()});
        if (session?.user) redirect('/');
    }
    return (
        <main className="auth-layout">
            <section className="auth-left-section scrollbar-hide-default">
                {/* Tope de ancho: sin el, en pantallas ultrawide (2560px) el
                    formulario se estiraba a ~1150px y las lineas de texto
                    ilegibles. */}
                <div className="mx-auto flex w-full max-w-md flex-col">
                    <Link href="/" className="auth-logo flex items-center gap-2">
                        <CavaAIWordmark />
                    </Link>

                    <div className="flex-1 pb-6 lg:pb-8">
                        {children}
                    </div>
                </div>
            </section>
            <section className="auth-right-section">
                <div className="lg:mt-4 lg:mb-16">
                    <blockquote className="auth-blockquote">
                        &ldquo;CavaAI convierte evidencia, memoria y modelos company-specific en una tesis que puedes contrastar con la realidad.&rdquo;
                    </blockquote>
                    <div className="flex items-center justify-end">
                        <div className="flex items-center gap-0.5">
                            {[1,2,3,4,5].map((star) => (
                                <Star aria-hidden="true" className="h-4 w-4 fill-teal-400 text-teal-400" key={star}/>
                            ))}
                        </div>
                    </div>
                </div>
                {/* Escala gray del tema, no slate: hasta ahora esta pantalla era
                    la unica con dos grises distintos (slate + gray) a la vez. */}
                <div className="flex-1 rounded-xl border border-gray-700/50 bg-surface-overlay p-6 shadow-2xl shadow-teal-950/20">
                    <div className="mb-6 flex items-start justify-between gap-4">
                        <div>
                            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal-300">Espacio de trabajo de la empresa</p>
                            <h2 className="mt-2 text-2xl font-semibold text-white">{productChain}</h2>
                        </div>
                        <LineChart aria-hidden="true" className="h-7 w-7 text-teal-300"/>
                    </div>
                    <div className="grid gap-3">
                        {productModules.map(({icon: ItemIcon, title, description}) => (
                                <div className="flex gap-4 rounded-lg border border-gray-700/50 bg-gray-800/50 p-4" key={title}>
                                    <ItemIcon aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-teal-300"/>
                                    <div>
                                        <p className="font-medium text-gray-100">{title}</p>
                                        <p className="mt-1 text-sm leading-6 text-gray-400">{description}</p>
                                    </div>
                                </div>
                        ))}
                    </div>
                </div>
            </section>

        </main>
    )
}
export default Layout
