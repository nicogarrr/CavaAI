'use client';

import { useOnlineStatus } from '@/hooks/useOnlineStatus';

export default function OnlineBanner() {
    const online = useOnlineStatus();
    
    if (online) return null;
    
    return (
        <div 
            role="status" 
            aria-live="polite" 
            className="w-full bg-yellow-100 text-yellow-800 text-sm py-2 px-4 text-center"
        >
            You are offline. Some data may be outdated until the connection is restored.
        </div>
    );
}

