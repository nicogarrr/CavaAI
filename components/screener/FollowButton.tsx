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
    <Button variant="ghost" size="sm" onClick={onClick} disabled={done || busy} className="h-7 px-2 text-xs text-gray-400 hover:text-teal-300">
      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : done ? <Check className="h-3.5 w-3.5 text-teal-400" /> : <Plus className="h-3.5 w-3.5" />}
      {done ? 'Siguiendo' : 'Seguir'}
    </Button>
  );
}
