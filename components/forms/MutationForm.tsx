'use client';

import { useRef, type ComponentPropsWithoutRef } from 'react';
import { toast } from 'sonner';
import { showErrorToast } from '@/lib/toast';

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

  async function submit(formData: FormData) {
    lastFormData.current = formData;
    try {
      await action(formData);
      if (resetOnSuccess) formRef.current?.reset();
      toast.success(successMessage);
    } catch (error) {
      // Toast accionable: si el motor está caído ofrece "Reintentar" con
      // los mismos datos del formulario.
      showErrorToast(error, {
        onRetry: async () => {
          const payload = lastFormData.current;
          if (payload) await submit(payload);
        },
        successMessage,
      });
    }
  }

  return (
    <form {...props} action={submit} ref={formRef}>
      {children}
    </form>
  );
}
