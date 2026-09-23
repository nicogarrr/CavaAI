'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { BellPlus, Loader2 } from 'lucide-react';
import { createAlert, type AlertType } from '@/lib/actions/alerts.actions';
import { toast } from 'sonner';
import { showErrorToast } from '@/lib/toast';

const ALERT_TYPES: Array<{ value: AlertType; label: string; needsValue: boolean; valuePlaceholder: string }> = [
  { value: 'price_above', label: 'Precio por encima de', needsValue: true, valuePlaceholder: 'Precio objetivo $' },
  { value: 'price_below', label: 'Precio por debajo de', needsValue: true, valuePlaceholder: 'Precio objetivo $' },
  { value: 'price_change', label: 'Cambio de precio %', needsValue: true, valuePlaceholder: 'Variación objetivo %' },
  { value: 'news', label: 'Nueva noticia', needsValue: false, valuePlaceholder: '' },
  { value: 'earnings', label: 'Reporte de ganancias', needsValue: false, valuePlaceholder: '' },
];

/**
 * Alerta rápida desde la ficha de research: selector de tipo de alerta y,
 * opcionalmente, deep-link a /alerts con el diálogo de creación
 * pre-rellenado para tipos más complejos.
 */
export default function QuickAlertButton({ ticker }: { ticker: string }) {
  const [type, setType] = useState<AlertType>('price_above');
  const [price, setPrice] = useState('');
  const [busy, setBusy] = useState(false);

  const meta = ALERT_TYPES.find((item) => item.value === type) ?? ALERT_TYPES[0];
  const numericValue = price.trim() === '' ? null : parseFloat(price);

  const onCreate = async () => {
    let value: number | string = '';
    if (meta.needsValue) {
      if (numericValue === null || !Number.isFinite(numericValue) || numericValue <= 0) {
        toast.error(
          type === 'price_change'
            ? 'Introduce una variación objetivo válida'
            : 'Introduce un precio objetivo válido',
        );
        return;
      }
      value = numericValue;
    }
    setBusy(true);
    try {
      await createAlert({
        symbol: ticker,
        type,
        condition: {
          operator: type === 'price_below' ? '<' : '>',
          value,
        },
      });
      toast.success(
        meta.needsValue
          ? `Alerta creada: ${ticker} ${meta.label.toLowerCase()} ${type === 'price_change' ? `${value}%` : `$${value}`}`
          : `Alerta creada: ${ticker} · ${meta.label}`,
      );
      setPrice('');
    } catch (error) {
      showErrorToast(error, {
        duplicateMessage: 'Ya tienes esta alerta configurada.',
        onRetry: onCreate,
      });
    } finally {
      setBusy(false);
    }
  };

  // El selector de tipo cubre la creación rápida; "Ver alertas" abre /alerts
  // (href exacto que espera el e2e) para tipos avanzados o edición.
  const deepLink = '/alerts';

  return (
    <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
      <Select value={type} onValueChange={(value: AlertType) => setType(value)}>
        <SelectTrigger
          aria-label="Tipo de alerta"
          className="h-11 w-full bg-[#101010] text-base sm:h-8 sm:w-48 sm:text-xs"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="bg-gray-900 border-gray-600">
          {ALERT_TYPES.map((item) => (
            <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      {meta.needsValue ? (
        <Input
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          type="number"
          min="0"
          step="0.01"
          inputMode="decimal"
          placeholder={meta.valuePlaceholder}
          aria-label={type === 'price_change' ? 'Variación objetivo en porcentaje' : 'Precio objetivo en dólares'}
          className="h-11 w-full bg-[#101010] text-base sm:h-8 sm:w-36 sm:text-xs"
        />
      ) : null}
      <div className="flex w-full gap-2 sm:w-auto">
        <Button size="sm" variant="outline" onClick={onCreate} disabled={busy} className="min-h-[44px] flex-1 gap-1.5 px-4 text-sm sm:min-h-0 sm:h-8 sm:flex-none sm:text-xs">
          {busy ? <Loader2 className="h-4 w-4 animate-spin sm:h-3.5 sm:w-3.5" /> : <BellPlus className="h-4 w-4 sm:h-3.5 sm:w-3.5" />}
          + Alerta
        </Button>
        <Button size="sm" variant="ghost" asChild className="min-h-[44px] flex-1 px-4 text-sm text-gray-300 sm:min-h-0 sm:h-8 sm:flex-none sm:text-xs">
          <Link href={deepLink}>Ver alertas</Link>
        </Button>
      </div>
    </div>
  );
}
