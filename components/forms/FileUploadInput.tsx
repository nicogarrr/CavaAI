'use client';

import { useEffect, useRef, useState, type ChangeEvent, type ComponentPropsWithoutRef } from 'react';
import { toast } from 'sonner';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

// Límite real de subida: next.config.ts → experimental.serverActions.bodySizeLimit = 4mb.
// Vercel Hobby corta el body de las server actions en ~4.5 MB, así que un archivo
// mayor falla siempre: se avisa al elegirlo y se bloquea el envío del formulario
// (botones de submit deshabilitados + submit interceptado + validación nativa).
export const MAX_UPLOAD_MB = 4;

type FileUploadInputProps = Omit<ComponentPropsWithoutRef<'input'>, 'type' | 'onChange'> & {
  maxMB?: number;
};

export function FileUploadInput({ maxMB = MAX_UPLOAD_MB, className, id, name, ...props }: FileUploadInputProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const tooBig = warning !== null;
  const inputId = id ?? name ?? 'file-upload';
  const warningId = `${inputId}-limite`;

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      setWarning(null);
      event.target.setCustomValidity('');
      return;
    }
    const limitBytes = maxMB * 1024 * 1024;
    if (file.size > limitBytes) {
      const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
      const message = `"${file.name}" pesa ${sizeMb} MB y el límite de subida es ${maxMB} MB: elige un archivo más pequeño o súbelo comprimido.`;
      setWarning(message);
      event.target.setCustomValidity(message);
      toast.warning(message);
    } else {
      setWarning(null);
      event.target.setCustomValidity('');
    }
  }

  // Bloquea el envío del formulario padre mientras el archivo supere el límite:
  // deshabilita sus botones de submit (marcados con data-upload-blocked para no
  // tocar los deshabilitados por otros motivos) e intercepta el submit
  // (cubre el envío con tecla Enter, que no pasa por el botón).
  useEffect(() => {
    const form = rootRef.current?.querySelector('input[type="file"]')?.closest('form');
    if (!form) return;
    const submits = Array.from(
      form.querySelectorAll<HTMLButtonElement | HTMLInputElement>(
        'button[type="submit"], input[type="submit"]'
      )
    );
    submits.forEach((el) => {
      if (tooBig) {
        if (!el.disabled) {
          el.disabled = true;
          el.dataset.uploadBlocked = '1';
        }
        el.setAttribute('aria-disabled', 'true');
      } else {
        if (el.dataset.uploadBlocked === '1') {
          el.disabled = false;
          delete el.dataset.uploadBlocked;
        }
        el.removeAttribute('aria-disabled');
      }
    });
    const onSubmit = (event: Event) => {
      if (tooBig) {
        event.preventDefault();
        event.stopPropagation();
        if (warning) toast.warning(warning);
      }
    };
    form.addEventListener('submit', onSubmit, true);
    return () => {
      form.removeEventListener('submit', onSubmit, true);
      submits.forEach((el) => {
        if (el.dataset.uploadBlocked === '1') {
          el.disabled = false;
          delete el.dataset.uploadBlocked;
        }
        el.removeAttribute('aria-disabled');
      });
    };
  }, [tooBig, warning]);

  return (
    <div ref={rootRef} className="w-full">
      <Input
        {...props}
        id={inputId}
        name={name}
        type="file"
        aria-invalid={tooBig}
        aria-describedby={warningId}
        className={cn(className, warning ? 'border-red-500' : null)}
        onChange={handleChange}
      />
      {warning ? (
        <p id={warningId} role="alert" className="mt-1 text-xs text-red-400">
          {warning} El envío está bloqueado hasta que elijas un archivo válido.
        </p>
      ) : (
        <p id={warningId} className="mt-1 text-xs text-gray-500">
          Máximo {maxMB} MB.
        </p>
      )}
    </div>
  );
}
