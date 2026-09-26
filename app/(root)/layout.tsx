import Breadcrumbs from "@/components/layout/Breadcrumbs";
import Header from "@/components/Header";
import Sidebar, { SIDEBAR_COLLAPSED_COOKIE } from "@/components/layout/Sidebar";
import OnlineBanner from "@/components/OnlineBanner";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { searchStocks } from "@/lib/actions/finnhub.actions";
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

/**
 * La lista inicial del buscador (Ctrl+K) llega por streaming y no debe bloquear
 * el primer pintado. Antes se envolvia en <Suspense> con un segundo <Header>
 * de fallback: eso montaba el arbol del header dos veces y hacia que el
 * buscador cambiase de contenido al resolver. Ahora se resuelve antes del
 * primer byte y el header se monta una sola vez; si la busqueda de acciones
 * populares falla, se entrega vacia y el buscador funciona equally por query.
 */
async function getInitialStocks(): Promise<StockWithWatchlistStatus[]> {
    return searchStocks().catch(() => []);
}

const Layout = async ({ children }: { children: React.ReactNode }) => {
    const user = await getLayoutUser();
    const [initialStocks, collapsed] = await Promise.all([
        getInitialStocks(),
        // Leido en servidor para que el sidebar plegado no de un flash de ancho
        // en la primera pintura (antes se leia en useEffect y salia expandido).
        cookies().then((jar) => jar.get(SIDEBAR_COLLAPSED_COOKIE)?.value === '1'),
    ]);

    return (
        <div className="flex min-h-dvh flex-col text-gray-300">
            <a href="#content" className="skip-link">Saltar al contenido</a>

            {/* Banner y header comparten un unico contenedor pegajoso: asi el
                aviso de "sin conexion" no desaparece al hacer scroll, y el
                alto de la zona pegajosa (--shell-top) queda derivado del propio
                DOM en vez de medido por JS. */}
            <div className="sticky top-0 z-50">
                <OnlineBanner />
                <Header user={user} initialStocks={initialStocks} />
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
