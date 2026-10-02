'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Check, Loader2, Plus } from 'lucide-react';
import { addToWatchlist, removeFromWatchlist } from '@/lib/actions/watchlist.actions';
import { toast } from 'sonner';
import { showErrorToast } from '@/lib/toast';

/**
 * Botón seguir/dejar de seguir con estado persistente.
 *
 * - `isFollowed` siembra el estado inicial desde el servidor (watchlist del
 *   usuario); sin él, el botón asume "no seguido" hasta la primera interacción.
 * - `stateUnknown` es el estado DESCONOCIDO: el backend de cartera falló y nadie
 *   sabe si sigues el ticker. No se pinta «Seguir» (sería una afirmación
 *   inventada) ni se ofrece «dejar de seguir» (la acción peor a ciegas): el
 *   botón queda deshabilitado y el hueco se DECLARA en texto, no solo en el
 *   tooltip (FIX-3.5).
 * - El toggle persiste en el backend (POST/DELETE /api/watchlist) y refresca
 *   la caché de /watchlist.
 * - Duplicados ("Ya sigues este ticker") y caídas del motor (toast con
 *   "Reintentar") se resuelven con showErrorToast.
 * - Contrato: `company` es solo etiqueta visual; la identidad del
 *   seguimiento es `symbol` (el backend lo normaliza a mayúsculas).
 */
export default function FollowButton({
  symbol,
  company,
  isFollowed = false,
  stateUnknown = false,
}: {
  symbol: string;
  company?: string;
  isFollowed?: boolean;
  /** El servidor no pudo leer la watchlist: no se sabe si se sigue. Botón deshabilitado, no un "Seguir" que podría ser falso. */
  stateUnknown?: boolean;
}) {
  const [followed, setFollowed] = useState(isFollowed);
  const [busy, setBusy] = useState(false);

  const onClick = async () => {
    if (busy) return;
    const action = followed ? 'remove' : 'add';
    setBusy(true);
    try {
      const res =
        action === 'remove'
          ? await removeFromWatchlist(symbol)
          : await addToWatchlist(symbol, company);

      if (res.success) {
        setFollowed(action === 'add');
        toast.success(
          action === 'add'
            ? `${symbol} añadido a la watchlist`
            : `${symbol} eliminado de la watchlist`,
        );
      } else {
        // Duplicado: el ticker ya estaba seguido; sincronizamos el estado visible.
        if (res.code === 'duplicate') setFollowed(true);
        showErrorToast(
          res.message ??
            (action === 'add'
              ? 'No se pudo añadir a la watchlist'
              : 'No se pudo eliminar de la watchlist'),
          {
          duplicateMessage: 'Ya sigues este ticker.',
          onRetry: onClick,
        });
      }
    } catch (error) {
      showErrorToast(error, { onRetry: onClick });
    } finally {
      setBusy(false);
    }
  };

  const button = (
    <Button
      variant="ghost"
      size="sm"
      onClick={onClick}
      disabled={busy || stateUnknown}
      title={stateUnknown ? 'No se pudo comprobar tu watchlist. Recarga la página.' : undefined}
      aria-busy={busy}
      aria-pressed={followed}
      className="min-h-[44px] px-3 py-2 text-sm text-gray-300 hover:text-teal-300 sm:h-7 sm:min-h-0 sm:px-2 sm:text-xs"
    >
      {busy ? (
        <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin sm:h-3.5 sm:w-3.5" />
      ) : followed ? (
        <Check aria-hidden="true" className="h-4 w-4 text-teal-400 sm:h-3.5 sm:w-3.5" />
      ) : (
        <Plus aria-hidden="true" className="h-4 w-4 sm:h-3.5 sm:w-3.5" />
      )}
      {busy ? 'Guardando…' : stateUnknown ? 'Seguir (no disponible)' : followed ? 'Dejar de seguir' : 'Seguir'}
    </Button>
  );

  // Estado desconocido: se DECLARA en texto, no solo en el tooltip. El botón va
  // deshabilitado —«dejar de seguir» a ciegas sería la acción peor, y «Seguir»
  // afirmaría una cartera que no se ha podido leer— pero el hueco se dice en
  // la propia cabecera (FIX-3.5).
  if (stateUnknown) {
    return (
      <span className="inline-flex min-h-[44px] flex-wrap items-center gap-2">
        <span aria-live="polite" className="text-xs text-amber-400">
          Seguimiento sin comprobar
        </span>
        {button}
      </span>
    );
  }

  return button;
}
