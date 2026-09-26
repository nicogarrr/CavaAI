/**
 * Guard de i18n. Fallo rapido y sin dependencias para dos regresiones concretas:
 *
 *  1. Una clave de `t()` que ya no existe en lib/i18n/es.json. En produccion
 *     `t()` devuelve la propia clave, asi que el usuario veria literalmente
 *     "common.states.empty" en pantalla.
 *  2. Un literal funcional en ingles reintroducido en app/ o components/. La
 *     app es es-ES y en el repo ya se colaron paginas enteras en ingles
 *     (app/(root)/screeners/[screenId]/page.tsx era un unico literal de 16
 *     lineas) y el boton de cerrar de todos los modales decia "Close".
 *
 * Solo se inspecciona TEXTO VISIBLE: el contenido de los literales de cadena y
 * los text nodes de JSX. Los identificadores (`isSubmitting`), los nombres de
 * funcion (`getMoatQualityScore`), los valores de atributo (`type="submit"`) y
 * las claves del backend no se tocan, porque ahi el ingles es legitimo.
 *
 * Uso: node scripts/check-i18n.mjs
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, extname } from "node:path";

const ROOT = process.cwd();
const es = JSON.parse(readFileSync(join(ROOT, "lib/i18n/es.json"), "utf8"));

/* ------------------------------------------------------------------ *
 * 1. Claves de t() que no existen
 * ------------------------------------------------------------------ */

const keyPaths = (node, prefix = "") => {
  if (node === null || typeof node !== "object" || Array.isArray(node)) return [prefix];
  return Object.entries(node).flatMap(([key, value]) =>
    keyPaths(value, prefix ? `${prefix}.${key}` : key),
  );
};

const validKeys = new Set(keyPaths(es));

const walk = (dir, out = []) => {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry.startsWith(".")) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if ([".ts", ".tsx"].includes(extname(full))) out.push(full);
  }
  return out;
};

const files = [
  ...walk(join(ROOT, "app")),
  ...walk(join(ROOT, "components")),
  ...walk(join(ROOT, "lib")),
];

const missingKeys = [];
for (const file of files) {
  const source = readFileSync(file, "utf8");
  for (const match of source.matchAll(/\bt\(\s*'([a-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)+)'/g)) {
    if (!validKeys.has(match[1])) {
      missingKeys.push(`${file.slice(ROOT.length + 1)}: ${match[1]}`);
    }
  }
}

/* ------------------------------------------------------------------ *
 * 2. Texto visible en ingles
 * ------------------------------------------------------------------ */

// Frases: coincidencia por contenida en un chunk de texto visible.
const ENGLISH_PHRASES = [
  "Loading...", "Loading…", "No results", "Search for a command", "Command Palette",
  "Show commands", "Something went wrong", "Try again", "Get started", "Learn more",
  "Read more", "Coming soon", "Under construction", "Not available", "No data",
  "Ticker Symbol", "Company Name", "Last Close", "Open Price",
  "Avg. Volume", "As of", "Updated at", "Created at", "Saved screen", "No match",
  "new match", "Portfolio totals exclude", "Work product",
  // Nulos: los canonicos son NA='N/D' y NO_CORRIDO='No corrido'.
  "N/A",
];

// Etiquetas enteras: coincidencia solo si el chunk ES la etiqueta.
const ENGLISH_LABELS = new Set([
  "Close", "Retry", "Undo", "Submit", "Cancel", "Delete", "Remove", "Dismiss",
  "Offline", "Not found", "Unknown", "Required", "Optional",
  "Example", "Missing", "PASS", "FAIL", "match", "Overview", "Settings",
  "Dashboard", "Welcome back", "Create account", "Sign in", "Sign out",
]);

// Se ignoran del todo los ficheros donde el ingles es correcto por diseno.
const ALLOW = [
  // Formato de datos parseados del backend, no copy de UI.
  "lib/utils/tableFormatter.ts",
  "lib/utils/tableExtractor.ts",
  "lib/glossary.ts",
  // Claves de objeto que viajan al data-engine, no etiquetas de interfaz.
  "lib/constants.ts",
  // server actions: sus "labels" son claves de registro del backend.
  "lib/actions/",
  // El propio diccionario.
  "lib/i18n/t.ts",
  "lib/i18n/es.json",
];

/** Texto visible de un fichero: literales de cadena y text nodes de JSX. */
const visibleChunks = (source) => {
  const chunks = [];
  const withoutComments = source
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/\/\/[^\n]*/g, (m) => m.replace(/[^\n]/g, " "));

  // Literales de cadena que NO son valores de atributo (`foo="bar"`).
  const literal = /(^|[=({\[,;:?&|!+\-*/%<>]\s*)('([^'\\\n]{2,})'|"([^"\\\n]{2,})"|`([^`\\]{2,})`)/g;
  for (const match of withoutComments.matchAll(literal)) {
    const value = match[3] ?? match[4] ?? match[5] ?? "";
    if (!/[\p{L}]/u.test(value)) continue;
    if (/^[a-z0-9_.-]+$/i.test(value) && !/[A-Z]/.test(value)) continue; // clave o enum
    chunks.push(value);
  }

  // Text nodes de JSX: >texto<
  for (const match of withoutComments.matchAll(/>([^<>{}]*[a-zA-ZáéíóúñÁÉÍÓÚÑ][^<>{}]*)</g)) {
    const value = match[1].trim();
    if (value) chunks.push(value);
  }

  return chunks;
};

const englishHits = [];
for (const file of files) {
  const rel = file.slice(ROOT.length + 1).replace(/\\/g, "/");
  if (ALLOW.some((prefix) => rel === prefix || rel.startsWith(prefix))) continue;
  const source = readFileSync(file, "utf8");
  for (const chunk of visibleChunks(source)) {
    const trimmed = chunk.trim();
    const line = source.slice(0, source.indexOf(chunk)).split("\n").length;
    if (ENGLISH_LABELS.has(trimmed)) {
      englishHits.push(`${rel}:~${line}  etiqueta  "${trimmed}"`);
      continue;
    }
    const phrase = ENGLISH_PHRASES.find((p) => trimmed.includes(p));
    if (phrase) englishHits.push(`${rel}:~${line}  "${phrase}"  ->  ${trimmed.slice(0, 80)}`);
  }
}

/* ------------------------------------------------------------------ */

const unique = [...new Set(englishHits)];

if (missingKeys.length > 0) {
  console.error(`\ni18n: ${missingKeys.length} clave(s) de t() que no existen en lib/i18n/es.json:`);
  for (const hit of missingKeys) console.error(`  - ${hit}`);
}

if (unique.length > 0) {
  console.error(`\ni18n: ${unique.length} literal(es) en ingles en app/ o components/:`);
  for (const hit of unique) console.error(`  - ${hit}`);
}

if (missingKeys.length > 0 || unique.length > 0) {
  console.error(
    "\nVer lib/i18n/README.md. Los anglicismos aceptados (Watchlist, Screeners, Sharpe, CAGR, PER (TTM)...) no deben aparecer aqui.\n",
  );
  process.exit(1);
}

console.log(
  `i18n ok: ${validKeys.size} claves, ${files.length} ficheros, 0 literales en ingles.`,
);
