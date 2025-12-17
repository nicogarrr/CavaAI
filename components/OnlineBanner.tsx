"use client";

import { useState, useEffect } from 'react';
import { useOnlineStatus } from "@/hooks/useOnlineStatus";

export const OnlineBanner = () => {
    const online = useOnlineStatus();
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
    }, []);

    // No renderizar nada hasta que el componente esté montado en el cliente
    if (!mounted || online) return null;

    return (
        <div role="status" aria-live="polite" className="w-full bg-yellow-100 text-yellow-800 text-sm py-2 px-4 text-center">
            You are offline. Some data may be outdated until the connection is restored.
        </div>
    );
};

export default OnlineBanner;
