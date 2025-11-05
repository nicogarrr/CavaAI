import Header from "@/components/Header";
import {getAuth} from "@/lib/better-auth/auth";
import {headers} from "next/headers";
import {redirect} from "next/navigation";
import Footer from "@/components/Footer";
import {searchStocks} from "@/lib/actions/finnhub.actions";
import React from "react";
import OnlineBanner from "@/components/OnlineBanner";

// Forzar renderizado dinámico porque usa headers() y requiere autenticación
export const dynamic = 'force-dynamic';
export const revalidate = 0;

const Layout = async ({ children }: { children : React.ReactNode }) => {
    try {
        const auth = await getAuth();
        if (!auth) redirect('/sign-in');
        
        const session = await auth.api.getSession({ headers: await headers() });

        if(!session?.user) redirect('/sign-in');

        const user = {
            id: session.user.id,
            name: session.user.name,
            email: session.user.email,
        }

        const initialStocks = await searchStocks().catch(() => []);

        return (
            <main className="min-h-screen text-gray-400">
                <OnlineBanner />
                <Header user={user} initialStocks={initialStocks} />

                <div className="container py-10">
                    {children}
                </div>

                <Footer />
            </main>
        )
    } catch (error) {
        // Log authentication errors for debugging while protecting user experience
        console.error('Error in layout:', error);
        
        // If authentication fails, redirect to sign-in
        // Usar try-catch adicional para evitar errores si redirect falla
        try {
            redirect('/sign-in');
        } catch (redirectError) {
            // Si redirect falla, retornar un layout básico de error
            return (
                <main className="min-h-screen text-gray-400 flex items-center justify-center">
                    <div className="text-center">
                        <h1 className="text-2xl font-bold mb-4">Error de autenticación</h1>
                        <p className="text-gray-500 mb-4">Por favor, inicia sesión nuevamente.</p>
                        <a href="/sign-in" className="text-teal-400 hover:text-teal-500">
                            Ir a inicio de sesión
                        </a>
                    </div>
                </main>
            );
        }
    }
}
export default Layout