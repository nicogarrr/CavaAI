import Header from "@/components/Header";
import { getAuth } from "@/lib/better-auth/auth";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { searchStocks } from "@/lib/actions/finnhub.actions";
import React from "react";
import OnlineBanner from "@/components/OnlineBanner";

// Forzar renderizado dinámico porque usa headers() y requiere autenticación
export const dynamic = 'force-dynamic';
export const revalidate = 0;

const Layout = async ({ children }: { children: React.ReactNode }) => {
    try {
        const auth = await getAuth();
        if (!auth) redirect('/sign-in');

        const session = await auth.api.getSession({ headers: await headers() });

        if (!session?.user) redirect('/sign-in');

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
            </main>
        )
    } catch (error) {
        // Log authentication errors for debugging while protecting user experience
        if (process.env.NODE_ENV === 'development') {
            console.error('Authentication error in layout:', error);
        }
        // If authentication fails, redirect to sign-in
        redirect('/sign-in');
    }
}
export default Layout