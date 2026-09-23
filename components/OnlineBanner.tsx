"use client";

import { useOnlineStatus } from "@/hooks/useOnlineStatus";

export const OnlineBanner = () => {
    const online = useOnlineStatus();
    if (online) return null;

    return (
        <div role="status" aria-live="polite" className="w-full bg-yellow-100 text-yellow-800 text-sm py-2 px-4 text-center">
            Sin conexión. Algunos datos pueden estar desactualizados hasta que se recupere la conexión.
        </div>
    );
};

export default OnlineBanner;
