import Header from "@/components/Header";
import Sidebar from "@/components/layout/Sidebar";
import OnlineBanner from "@/components/OnlineBanner";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { searchStocks } from "@/lib/actions/finnhub.actions";
import { requireAuthenticatedUser } from "@/lib/auth/require-user";
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
    const initialStocks = await searchStocks().catch(() => []);

    return (
        <main className="min-h-screen text-gray-400">
            <OnlineBanner />
            <Header user={user} initialStocks={initialStocks} />

            <div className="flex items-start">
                <Sidebar />
                <div className="container py-10 flex-1 min-w-0">
                    <ErrorBoundary>
                        {children}
                    </ErrorBoundary>
                </div>
            </div>
        </main>
    );
};

export default Layout;
