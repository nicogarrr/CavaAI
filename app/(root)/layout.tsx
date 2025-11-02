import Header from "@/components/Header";
import {getAuth} from "@/lib/better-auth/auth";
import {headers} from "next/headers";
import {redirect} from "next/navigation";
import Footer from "@/components/Footer";
import {searchStocks} from "@/lib/actions/finnhub.actions";

// Forzar renderizado dinámico porque usa headers() y requiere autenticación
export const dynamic = 'force-dynamic';
export const revalidate = 0;

const Layout = async ({ children }: { children : React.ReactNode }) => {
    try {
        const auth = await getAuth();
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
                <Header user={user} initialStocks={initialStocks} />

                <div className="container py-10">
                    {children}
                </div>

                <Footer />
            </main>
        )
    } catch (error) {
        console.error('Error in layout:', error);
        // Si hay error, redirigir a sign-in
        redirect('/sign-in');
    }
}
export default Layout