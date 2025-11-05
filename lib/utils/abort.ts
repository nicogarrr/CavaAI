export function withTimeout(signal: AbortSignal | undefined, timeoutMs: number): AbortSignal {
  const controller = new AbortController();

  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  if (signal) {
    signal.addEventListener('abort', () => controller.abort(), { once: true });
  }

  // Importante: quien llame debe limpiar el timeout cuando termine el fetch
  // Devolvemos un signal que abortará al cumplirse el timeout o si el signal original aborta
  // El caller debe clearTimeout(timeoutId) tras el fetch
  // Para simplificar, exponemos también el timeoutId
  // Pero en TS puro, devolvemos solo el signal; el caller puede recrear esta utilidad si necesita el id
  // Aquí mantenemos la API simple

  // @ts-expect-error attach for internal use by callers that know
  controller.timeoutId = timeoutId;
  return controller.signal;
}


