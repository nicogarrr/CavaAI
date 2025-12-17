'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Trash2 } from 'lucide-react';
import { removeFromWatchlist } from '@/lib/actions/watchlist.actions';
import { useRouter } from 'next/navigation';

interface WatchlistRemoveButtonProps {
    symbol: string;
}

export default function WatchlistRemoveButton({ symbol }: WatchlistRemoveButtonProps) {
    const router = useRouter();
    const [loading, setLoading] = useState(false);

    const handleRemove = async () => {
        setLoading(true);
        await removeFromWatchlist(symbol);
        router.refresh();
        setLoading(false);
    };

    return (
        <Button
            variant="ghost"
            size="icon"
            onClick={handleRemove}
            disabled={loading}
            className="text-gray-500 hover:text-red-400 hover:bg-red-900/20"
            title="Eliminar de Watchlist"
        >
            <Trash2 className="w-4 h-4" />
        </Button>
    );
}
