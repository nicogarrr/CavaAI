import Header from "@/components/Header";
import {getAuth} from "@/lib/better-auth/auth";
import {headers} from "next/headers";
import {redirect} from "next/navigation";
import Footer from "@/components/Footer";
import {searchStocks} from "@/lib/actions/finnhub.actions";

const Layout = async ({ children }: { children : React.ReactNode }) => {
    const auth = await getAuth();
    const session = await auth.api.getSession({ headers: await headers() });

    if(!session?.user) redirect('/sign-in');

    const user = {
        id: session.user.id,
        name: session.user.name,
        email: session.user.email,
    }

    const initialStocks = await searchStocks();

    return (
        <main className="min-h-screen text-gray-400">
            <Header user={user} initialStocks={initialStocks} />

            <div className="container py-10">
                {children}
            </div>

            <Footer />
        </main>
    )
}
export default Layout