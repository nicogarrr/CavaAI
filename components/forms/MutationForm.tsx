'use client';

import { useRef, useState, type ComponentPropsWithoutRef } from 'react';
import { toast } from 'sonner';
import { showErrorToast } from '@/lib/toast';
import { getFriendlyErrorMessage, isNextRedirectError } from '@/lib/types/errors';

type MutationFormProps = Omit<ComponentPropsWithoutRef<'form'>, 'action'> & {
  action: (formData: FormData) => Promise<unknown>;
  successMessage?: string;
  resetOnSuccess?: boolean;
};

export function MutationForm({
  action,
  children,
  successMessage = 'Operación completada',
  resetOnSuccess = false,
  ...props
}: MutationFormProps) {
  const formRef = useRef<HTMLFormElement>(null);
  const lastFormData = useRef<FormData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);

  async function submit(formData: FormData) {
    if (isPending) return;
    lastFormData.current = formData;
    setError(null);
    setIsPending(true);
    try {
      await action(formData);
      if (resetOnSuccess) formRef.current?.reset();
      toast.success(successMessage);
    } catch (err) {
      // Los redirects de Next forman parte de la navegación: re-lanzarlos.
      if (isNextRedirectError(err)) throw err;
      // Error inline visible + toast accionable: ningún submit falla en silencio.
      setError(getFriendlyErrorMessage(err));
      // Toast accionable: si el motor está caído ofrece "Reintentar" con
      // los mismos datos del formulario.
      showErrorToast(err, {
        onRetry: async () => {
          const payload = lastFormData.current;
          if (payload) await submit(payload);
        },
        successMessage,
      });
    } finally {
      setIsPending(false);
    }
  }

  return (
    <form {...props} action={submit} aria-busy={isPending} ref={formRef}>
      {isPending ? (
        <span aria-live="polite" role="status" className="sr-only">
          Enviando formulario
        </span>
      ) : null}
      <fieldset disabled={isPending} className="contents">
        {children}
      </fieldset>
      {error ? (
        <p className="mt-3 text-sm text-red-300" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}
