/**
 * Tipos del detector compartido de `'use client'`.
 *
 * El modulo es `.mjs` (lo consumen tanto un script plano de node como el guard
 * bajo `--experimental-strip-types`), asi que los tipos viven aqui para que el
 * guard los compruebe de verdad en vez de mirar `any`.
 */

/** Un fichero ya parseado: si tiene la directiva y que senales emite. */
export interface AnalyzedSource {
  /** Ruta relativa al repo, siempre con `/` (los importadores usan posix). */
  rel: string;
  text: string;
  /** La directiva esta en el prologo, no en medio del fichero. */
  hasUseClient: boolean;
  /** Senales detectadas: hooks, handlers JSX, globales de navegador, etc. */
  signals: Set<string>;
  /** Especificadores de import, incluidos los de `dynamic(() => import(..))`. */
  imports: Set<string>;
}

/** Veredicto sobre un fichero: es su `'use client'` justificable? */
export interface AuditRow {
  rel: string;
  hasUseClient: boolean;
  /** Todas las senales, incluidas las que NO justifican (useMemo/useCallback). */
  signals: string[];
  /** Senales que por si solas justifican la directiva. */
  hardSignals: string[];
  /** Subconjunto de `hardSignals` que son indirecciones no desmentibles. */
  unprovable: string[];
  /** Modulos del repo importados que ya son cliente. */
  importsClientModule: string[];
  /** Paquetes que solo funcionan en cliente. */
  clientPkgs: string[];
  justified: boolean;
  /** Por que: las señales duras, la libreria y los modulos cliente importados. */
  reasons: string[];
  /** Lo importa un Client Component: quitar la directiva no ahorra un byte. */
  inheritedFromClient: boolean;
  /** Quien importa este fichero. */
  importers: string[];
}

export declare const CLIENT_HOOKS: Set<string>;
export declare const SERVER_SAFE_HOOKS: Set<string>;
export declare const NEXT_NAV_HOOKS: Set<string>;
export declare const REACT_DOM_HOOKS: Set<string>;
export declare const BROWSER_GLOBALS: Set<string>;
export declare const CLIENT_ONLY_PKGS: string[];
export declare const SERVER_SAFE_PKGS: string[];
/** Senales que NO justifican la directiva por si solas (`useMemo`, `useCallback`). */
export declare const NON_JUSTIFYING_SIGNALS: Set<string>;
/** Senales aceptadas por no ser desmentibles (`{...props}`, `next/dynamic`). */
export declare const UNPROVABLE_SIGNALS: Set<string>;

export declare function isClientOnlyPkg(spec: string): boolean;
export declare function listSourceFiles(absDir: string, out?: string[]): string[];
/** True solo si el literal es el PRIMER statement del fichero. */
export declare function hasUseClientDirective(text: string): boolean;
export declare function analyzeSource(rel: string, text: string): AnalyzedSource;
/** Resuelve un especificador relativo o `@/` a una ruta del repo, o null. */
export declare function resolveImport(fromRel: string, spec: string, known: Set<string>): string | null;
export declare function auditUseClient(analyzedList: AnalyzedSource[]): AuditRow[];
/** Atajo: lista, lee y audita los `.tsx?` de varios subdirectorios del repo. */
export declare function auditRepo(repoRoot: string, subdirs: string[]): AuditRow[];
