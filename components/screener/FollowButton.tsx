'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Check, Loader2, Plus } from 'lucide-react';
import { addToWatchlist } from '@/lib/actions/watchlist.actions';
import { toast } from 'sonner';

export default function FollowButton({ symbol, company }: { symbol: string; company?: string }) {
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const onClick = async () => {
    if (done || busy) return;
    setBusy(true);
    try {
      const res = await addToWatchlist(symbol, company);
      if (res.success) {
        setDone(true);
        toast.success(`${symbol} añadido a la watchlist`);
      } else {
        toast.error('No se pudo añadir a la watchlist');
      }
    } catch {
      toast.error('No se pudo añadir a la watchlist');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={onClick}
      disabled={done || busy}
      className="min-h-[44px] px-3 py-2 text-sm text-gray-300 hover:text-teal-300 sm:h-7 sm:min-h-0 sm:px-2 sm:text-xs"
    >
      {busy ? <Loader2 className="h-4 w-4 animate-spin sm:h-3.5 sm:w-3.5" /> : done ? <Check className="h-4 w-4 text-teal-400 sm:h-3.5 sm:w-3.5" /> : <Plus className="h-4 w-4 sm:h-3.5 sm:w-3.5" />}
      {done ? 'Siguiendo' : 'Seguir'}
    </Button>
  );
}
