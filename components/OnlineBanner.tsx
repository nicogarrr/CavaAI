"use client";

import { useOnlineStatus } from "@/hooks/useOnlineStatus";

/**
 * Aviso de conexion. Se renderiza en flujo normal justo encima del header, asi
 * que el header sticky (top-0) queda por debajo en el eje de apilado y el
 * aviso nunca queda tapado ni se va al hacer scroll: es exactamente lo que
 * necesita saber el usuario cuando la app esta mostrando datos rancios.
 */
export const OnlineBanner = () => {
    const online = useOnlineStatus();
    if (online) return null;

    return (
        <div
            role="status"
            aria-live="polite"
            data-online-banner
            className="w-full bg-amber-100 py-2 text-center text-sm text-amber-900"
        >
            Sin conexión. Algunos datos pueden estar desactualizados hasta que se recupere la conexión.
        </div>
    );
};

export default OnlineBanner;
