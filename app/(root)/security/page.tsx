import { redirect } from "next/navigation";
import { requireAuthenticatedUser } from "@/lib/auth/require-user";
import { getTwoFactorStatus } from "@/lib/actions/auth.actions";
import TwoFactorSettings from "@/components/security/TwoFactorSettings";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function SecurityPage() {
    let user;
    try {
        user = await requireAuthenticatedUser();
    } catch {
        redirect("/sign-in");
    }

    const status = await getTwoFactorStatus();

    return (
        <main id="content" tabIndex={-1} className="space-y-8">
            <div>
                <h1 className="text-2xl font-bold text-white">Seguridad</h1>
                <p className="text-sm text-gray-400 mt-1">
                    Ajustes de seguridad de la cuenta de <span className="text-gray-200">{user.email}</span>.
                </p>
            </div>

            <TwoFactorSettings initiallyEnabled={status.success ? Boolean(status.enabled) : false} />
        </main>
    );
}
