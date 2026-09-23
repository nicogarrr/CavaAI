'use client';

import { useState, type ChangeEvent, type ComponentPropsWithoutRef } from 'react';
import { toast } from 'sonner';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

// Límite real de subida: next.config.ts → experimental.serverActions.bodySizeLimit = 4mb.
// Vercel Hobby corta el body de las server actions en ~4.5 MB, así que un archivo
// mayor falla siempre: se avisa al elegirlo, antes de un envío inútil.
export const MAX_UPLOAD_MB = 4;

type FileUploadInputProps = Omit<ComponentPropsWithoutRef<'input'>, 'type' | 'onChange'> & {
  maxMB?: number;
};

export function FileUploadInput({ maxMB = MAX_UPLOAD_MB, className, ...props }: FileUploadInputProps) {
  const [warning, setWarning] = useState<string | null>(null);

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      setWarning(null);
      return;
    }
    const limitBytes = maxMB * 1024 * 1024;
    if (file.size > limitBytes) {
      const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
      const message = `"${file.name}" pesa ${sizeMb} MB y el límite de subida es ${maxMB} MB: la subida fallará. Divide el archivo o súbelo comprimido.`;
      setWarning(message);
      toast.warning(message);
    } else {
      setWarning(null);
    }
  }

  return (
    <div className="w-full">
      <Input
        {...props}
        type="file"
        className={cn(className, warning ? 'border-red-500' : null)}
        onChange={handleChange}
      />
      {warning ? (
        <p className="mt-1 text-xs text-red-400">{warning}</p>
      ) : (
        <p className="mt-1 text-xs text-gray-500">Máximo {maxMB} MB.</p>
      )}
    </div>
  );
}
