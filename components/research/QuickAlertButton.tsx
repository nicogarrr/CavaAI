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
    <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
      <Input
        value={price}
        onChange={(e) => setPrice(e.target.value)}
        type="number"
        min="0"
        step="0.01"
        inputMode="decimal"
        placeholder="Precio objetivo $"
        aria-label="Precio objetivo en dólares"
        className="h-11 w-full bg-[#101010] text-base sm:h-8 sm:w-36 sm:text-xs"
      />
      <div className="flex w-full gap-2 sm:w-auto">
        <Button size="sm" variant="outline" onClick={onCreate} disabled={busy} className="min-h-[44px] flex-1 gap-1.5 px-4 text-sm sm:min-h-0 sm:h-8 sm:flex-none sm:text-xs">
          {busy ? <Loader2 className="h-4 w-4 animate-spin sm:h-3.5 sm:w-3.5" /> : <BellPlus className="h-4 w-4 sm:h-3.5 sm:w-3.5" />}
          + Alerta
        </Button>
        <Button size="sm" variant="ghost" asChild className="min-h-[44px] flex-1 px-4 text-sm text-gray-300 sm:min-h-0 sm:h-8 sm:flex-none sm:text-xs">
          <Link href="/alerts">Ver alertas</Link>
        </Button>
      </div>
    </div>
  );
}
