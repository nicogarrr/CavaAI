import { expect, test } from "@playwright/test";

// Guard de regresión (bug d del lote log-hygiene, 2026-10-12).
//
// Contexto: el log de un run e2e del 11/10 mostró un warning de hidratación
// de React 19 en /propicks sobre el input oculto del Slider Radix
// (SliderBubbleInput): el SSR servia style="display:none;caret-color:transparent"
// y el cliente {display:"none"}.
//
// Investigacion de causa raiz (12/10, rama instinct/fix-log-hygiene):
// - Direccion del diff verificada en el source de React 19.2
//   (react-dom-client.development.js, diffHydratedStyles):
//   "-" = atributo DOM servido por el SSR, "+" = props del cliente.
// - "caret-color" NO aparece en: todo el repo, components/ui/slider.tsx,
//   NINGUNA version publicada de @radix-ui/react-slider (tarballs npm
//   1.0.0, 1.1.0, 1.1.1, 1.1.2, 1.2.3 y la 1.3.6 instalada, mas el source
//   main en GitHub), ni en los chunks .next del dev server.
// - No reproducible en codigo actual: run completo del spec
//   methodology-disclosure + cargas directas de /propicks /risk /portfolio
//   /plan con captura de consola = 0 ocurrencias.
// Conclusion: el SSR de aquel run venia de un artefacto de entorno (chunk
// compilado stale/mezclado), no del source. No hay fix honesto que aplicar;
// este guard caza el warning si alguna vez vuelve, con contexto.
//
// Nota: en entornos sin datos del embudo, /propicks renderiza
// ProPicksLoadError (sin Slider) y el guard ejercita solo ese estado; en el
// suite completo con datos ejercita la pagina real con filtros y Slider.

test.skip(!process.env.E2E_UI_RUN, "Set E2E_UI_RUN=1 to run browser tests.");

const HYDRATION_PATTERNS = [
  "An error occurred during hydration",
  "Hydration failed",
  "did not match. Server-rendered HTML",
  "A tree hydrated but some attributes",
  "caret-color",
];

for (const vp of [
  { name: "desktop", width: 1440, height: 900 },
  { name: "movil", width: 390, height: 844 },
]) {
  test(`/propicks sin warnings de hidratacion (${vp.name})`, async ({ page }) => {
    const consoleLines: string[] = [];
    page.on("console", (m) => consoleLines.push(m.text()));
    page.on("pageerror", (e) => consoleLines.push(String(e)));

    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto("/propicks", { waitUntil: "networkidle", timeout: 60000 });
    // Margen para hidratacion tardia de boundaries Suspense streameados.
    await page.waitForTimeout(4000);

    const hits = consoleLines.filter((l) =>
      HYDRATION_PATTERNS.some((p) => l.includes(p))
    );
    expect(
      hits,
      `warnings de hidratacion en /propicks (${vp.name}):\n${hits.join("\n").slice(0, 2000)}`
    ).toEqual([]);
  });
}
