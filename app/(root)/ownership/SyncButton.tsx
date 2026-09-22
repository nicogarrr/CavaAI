'use client';

import { useTransition } from 'react';
import { RefreshCw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { syncOwnershipManagers } from '@/lib/actions/ownership.actions';

export default function SyncButton() {
    const [pending, startTransition] = useTransition();
    return (
        <Button
            disabled={pending}
            onClick={() => startTransition(async () => { await syncOwnershipManagers(); })}
        >
            <RefreshCw className={`h-4 w-4 ${pending ? 'animate-spin' : ''}`} />
            {pending ? 'Sincronizando…' : 'Sincronizar 13F'}
        </Button>
    );
}
