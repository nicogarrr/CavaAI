import Breadcrumbs from "@/components/layout/Breadcrumbs";
import Header from "@/components/Header";
import Sidebar, { SIDEBAR_COLLAPSED_COOKIE } from "@/components/layout/Sidebar";
import OnlineBanner from "@/components/OnlineBanner";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { requireAuthenticatedUser } from "@/lib/auth/require-user";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import React from "react";

export const dynamic = "force-dynamic";
export const revalidate = 0;

async function getLayoutUser(): Promise<User> {
    try {
        const user = await requireAuthenticatedUser();
        return {
            id: user.id,
            name: user.name ?? user.email ?? 'Usuario',
            email: user.email ?? '',
        };
    } catch {
        redirect("/sign-in");
    }
}

const Layout = async ({ children }: { children: React.ReactNode }) => {
    const user = await getLayoutUser();
    // Las populares del buscador NO se esperan aqui: resolverlas antes del
    // primer byte retrasaba el TTFB de CADA pagina autenticada (llamada
    // Finnhub/DB) aunque el usuario nunca abriese el buscador. SearchCommand
    // las carga perezosamente al abrirse por primera vez y las reutiliza el
    // resto de la sesion; el header se monta una sola vez igualmente.
    const collapsed = await cookies().then(
        (jar) => jar.get(SIDEBAR_COLLAPSED_COOKIE)?.value === '1',
    );

    return (
        <div className="flex min-h-dvh flex-col text-gray-300">
            <a href="#content" className="skip-link">Saltar al contenido</a>

            {/* Banner y header comparten un unico contenedor pegajoso: asi el
                aviso de "sin conexion" no desaparece al hacer scroll, y el
                alto de la zona pegajosa (--shell-top) queda derivado del propio
                DOM en vez de medido por JS. */}
            <div className="sticky top-0 z-50">
                <OnlineBanner />
                <Header user={user} />
            </div>

            <div className="flex flex-1 items-start">
                <Sidebar collapsed={collapsed} />
                <div className="min-w-0 flex-1 px-4 py-5 md:px-6 md:py-6 lg:px-8">
                    <Breadcrumbs />
                    <ErrorBoundary>
                        {children}
                    </ErrorBoundary>
                </div>
            </div>
        </div>
    );
};

export default Layout;
