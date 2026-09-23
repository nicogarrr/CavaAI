/**
 * Supuestos visibles de los escenarios bear/base/bull.
 *
 * Los spreads son los reales del motor (long_term_model_service.py:
 * bear/bull con ±spread de crecimiento y margen, WACC +2pp/−1pp; el
 * standard_dcf.py usa la misma parrilla ±8pp crecimiento, ±6pp margen).
 * Se muestra dentro de un <details> para no saturar la vista principal.
 */
export default function ScenarioAssumptions() {
  return (
    <details className="mt-3 rounded-lg border border-gray-800 bg-black/20 px-4 py-3 text-sm">
      <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-gray-400">
        Supuestos del escenario
      </summary>
      <div className="mt-3 space-y-2 text-xs leading-5 text-gray-400">
        <p>
          <span className="font-semibold text-gray-300">Bear:</span> crecimiento de ingresos
          −hasta 8pp (mínimo 2pp de ajuste), margen FCF −hasta 6pp (suelo 0%) y WACC +2pp
          (crecimiento terminal −0,5pp). Impulsores: ejecución adversa, compresión de margen y
          capital más caro.
        </p>
        <p>
          <span className="font-semibold text-gray-300">Base:</span> supuestos normalizados sobre
          hechos históricos (CAGR de ingresos y margen FCF normalizado), sin ajustes de escenario.
          Es el ancla, no una predicción puntual.
        </p>
        <p>
          <span className="font-semibold text-gray-300">Bull:</span> crecimiento +hasta 8pp (techo
          50%), margen FCF +hasta 6pp (techo 60%) y WACC −1pp (suelo: crecimiento terminal +1pp).
          Impulsores: ejecución favorable, expansión de margen y capital más barato.
        </p>
        <p className="border-t border-gray-800 pt-2 text-gray-500">
          Los spreads se ajustan a la volatilidad histórica de cada compañía (entre 2pp y el máximo
          indicado). Las probabilidades de cada escenario se derivan de la confianza de la evidencia
          y del sesgo de crecimiento histórico, no de opiniones del modelo.
        </p>
      </div>
    </details>
  );
}
