'use client';

import { useRef, type ComponentPropsWithoutRef } from 'react';
import { toast } from 'sonner';
import { getErrorMessage } from '@/lib/types/errors';

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

  async function submit(formData: FormData) {
    try {
      await action(formData);
      if (resetOnSuccess) formRef.current?.reset();
      toast.success(successMessage);
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  return (
    <form {...props} action={submit} ref={formRef}>
      {children}
    </form>
  );
}
