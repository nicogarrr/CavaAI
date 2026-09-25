'use client';

import { useFormStatus } from 'react-dom';
import { Loader2, Play } from 'lucide-react';

import { Button } from '@/components/ui/button';

/**
 * Botón de submit para el form ad-hoc de screeners (GET server-side):
 * muestra spinner y se deshabilita durante la navegación, para que el
 * envío nunca parezca silencioso.
 */
export function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <Button aria-disabled={pending} disabled={pending} type="submit">
      {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
      {pending ? 'Ejecutando…' : 'Ejecutar'}
    </Button>
  );
}
