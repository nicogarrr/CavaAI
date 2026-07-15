import Link from "next/link";
import React from "react";
import {headers} from "next/headers";
import {redirect} from "next/navigation";
import {getAuth} from "@/lib/better-auth/auth";
import {CavaAIWordmark} from "@/components/CavaAIWordmark";
import {Database, FileSearch, GitBranch, LineChart, Star} from "lucide-react";

// Forzar renderizado dinámico porque usa headers() para verificar sesión
export const dynamic = 'force-dynamic';
export const revalidate = 0;

const productModules = [
    { icon: FileSearch, title: 'Evidence', description: 'Facts and claims keep their source lineage.' },
    { icon: Database, title: 'Long-Term Model', description: 'Drivers and assumptions adapt to the company.' },
    { icon: GitBranch, title: 'Expectation vs Reality', description: 'Reported outcomes review each forecast.' },
];

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
                <Link href="/" className="auth-logo flex items-center gap-2">
                    <CavaAIWordmark />
                </Link>

                <div className="pb-6 lg:pb-8 flex-1">
                    {children}
                </div>
            </section>
            <section className="auth-right-section">
                <div className="z-10 relative lg:mt-4 lg:mb-16">
                    <blockquote className="auth-blockquote">
                        &ldquo;CavaAI convierte evidencia, memoria y modelos company-specific en una tesis que puedes contrastar con la realidad.&rdquo;
                    </blockquote>
                    <div className="flex items-center justify-end">
                        <div className="flex items-center gap-0.5">
                            {[1,2,3,4,5].map((star) => (
                                <Star aria-hidden="true" className="h-4 w-4 fill-slate-300 text-slate-300" key={star}/>
                            ))}
                        </div>
                    </div>
                </div>
                <div className="flex-1 rounded-2xl border border-slate-800 bg-slate-950/70 p-6 shadow-2xl shadow-teal-950/20">
                    <div className="mb-6 flex items-start justify-between gap-4">
                        <div>
                            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal-300">Company workspace</p>
                            <h2 className="mt-2 text-2xl font-semibold text-white">Evidence → Model → Thesis</h2>
                        </div>
                        <LineChart aria-hidden="true" className="h-7 w-7 text-teal-300"/>
                    </div>
                    <div className="grid gap-3">
                        {productModules.map(({icon: ItemIcon, title, description}) => (
                                <div className="flex gap-4 rounded-xl border border-slate-800 bg-slate-900/70 p-4" key={title}>
                                    <ItemIcon aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-teal-300"/>
                                    <div>
                                        <p className="font-medium text-slate-100">{title}</p>
                                        <p className="mt-1 text-sm leading-6 text-slate-400">{description}</p>
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
