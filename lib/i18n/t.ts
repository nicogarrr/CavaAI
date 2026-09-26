/**
 * i18n mínima del repo: un diccionario (es.json) y un accessor con tipos.
 *
 * Por qué NO next-intl: la app es íntegramente es-ES, no hay enrutado por
 * locale ni i18n de terceros. next-intl añade middleware, carga de mensajes
 * por request y un provider de cliente paraTranslatedMessage
 * (precarga de mensajes) que aquí no se usan. Con un JSON + una función
 * tipada por `typeof es` se consigue lo mismo (te autocompletado de claves y
 * error en desarrollo si te equivocas al escribir la clave) sin dependencias.
 *
 * Módulo puro: se importa igual desde server y client components.
 */

import es from './es.json';

export { es };

type Leaves<T> = {
  [K in keyof T]: T[K] extends string ? K : Leaves<T[K]>;
}[keyof T];

/** Claves aceptadas: "portfolio.tearsheet.maxDrawdown" (hoja del diccionario). */
export type TranslationKey = Leaves<typeof es>;

/** Variables `{name}` de una clave. */
export type TranslationVars = Record<string, string | number>;

function lookup(path: string): unknown {
  return path
    .split('.')
    .reduce<unknown>(
      (node, key) =>
        node !== null && typeof node === 'object'
          ? (node as Record<string, unknown>)[key]
          : undefined,
      es as unknown,
    );
}

/**
 * Traduce una clave del diccionario.
 *
 * - Sustituye `{name}` por los valores de `vars`.
 * - En DESARROLLO lanza si la clave no existe o falta una variable: es un
 *   error de programación y debe verse en la consola, no como `{n}` en
 *   pantalla ni como un "N/D" silencioso.
 * - En PRODUCCIÓN devuelve la propia clave: la UI se mantiene legible y no se
 *   rompe la página por un texto que falta.
 */
export function t(path: TranslationKey, vars?: TranslationVars): string;
export function t(path: string, vars?: TranslationVars): string;
export function t(path: string, vars?: TranslationVars): string {
  const value = lookup(path);
  if (typeof value !== 'string') {
    if (process.env.NODE_ENV !== 'production') {
      throw new Error(`[i18n] Falta la clave "${path}" en lib/i18n/es.json`);
    }
    return path;
  }
  if (!vars) return value;
  return value.replace(/\{(\w+)\}/g, (match, name: string) => {
    const replacement = vars[name];
    if (replacement === undefined) {
      if (process.env.NODE_ENV !== 'production') {
        throw new Error(`[i18n] Falta la variable "{${name}}" para la clave "${path}"`);
      }
      return match;
    }
    return String(replacement);
  });
}
