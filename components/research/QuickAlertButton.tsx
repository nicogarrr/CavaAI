'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { BellPlus, Loader2 } from 'lucide-react';
import { createAlert } from '@/lib/actions/alerts.actions';
import { toast } from 'sonner';
import { getErrorMessage } from '@/lib/types/errors';

export default function QuickAlertButton({ ticker }: { ticker: string }) {
  const [price, setPrice] = useState('');
  const [busy, setBusy] = useState(false);

  const onCreate = async () => {
    const value = parseFloat(price);
    if (!Number.isFinite(value) || value <= 0) {
      toast.error('Introduce un precio objetivo válido');
      return;
    }
    setBusy(true);
    try {
      await createAlert({ symbol: ticker, type: 'price_above', condition: { operator: '>', value } });
      toast.success(`Alerta creada: ${ticker} por encima de $${value}`);
      setPrice('');
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Input
        value={price}
        onChange={(e) => setPrice(e.target.value)}
        type="number"
        min="0"
        step="0.01"
        placeholder="Precio objetivo $"
        className="h-8 w-36 bg-[#101010] text-xs"
      />
      <Button size="sm" variant="outline" onClick={onCreate} disabled={busy} className="h-8 gap-1.5 text-xs">
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <BellPlus className="h-3.5 w-3.5" />}
        + Alerta
      </Button>
      <Button size="sm" variant="ghost" asChild className="h-8 text-xs text-gray-400">
        <Link href="/alerts">Ver alertas</Link>
      </Button>
    </div>
  );
}
