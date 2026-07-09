import Header from "@/components/Header";
import OnlineBanner from "@/components/OnlineBanner";
import { searchStocks } from "@/lib/actions/finnhub.actions";
import { getAuth } from "@/lib/better-auth/auth";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import React from "react";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const DEV_USER = {
    id: "dev-user-123",
    name: "CavaAI Dev",
    email: "dev@cavaai.local",
};

async function getLayoutUser(): Promise<User> {
    try {
        const auth = await getAuth();
        if (!auth) {
            if (process.env.NODE_ENV === "development") return DEV_USER;
            redirect("/sign-in");
        }

        const session = await auth.api.getSession({ headers: await headers() });
        if (!session?.user) {
            if (process.env.NODE_ENV === "development") return DEV_USER;
            redirect("/sign-in");
        }

        return {
            id: session.user.id,
            name: session.user.name,
            email: session.user.email,
        };
    } catch (error) {
        if (process.env.NODE_ENV === "development") {
            console.warn("Using development auth fallback in root layout:", error);
            return DEV_USER;
        }
        redirect("/sign-in");
    }
}

const Layout = async ({ children }: { children: React.ReactNode }) => {
    const user = await getLayoutUser();
    const initialStocks = await searchStocks().catch(() => []);

    return (
        <main className="min-h-screen text-gray-400">
            <OnlineBanner />
            <Header user={user} initialStocks={initialStocks} />

            <div className="container py-10">
                {children}
            </div>
        </main>
    );
};

export default Layout;
