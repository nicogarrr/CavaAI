/** Ejemplo didáctico, no cotizaciones reales. Resultado por acción al vencimiento. */
export function OptionPayoff() {
  return (
    <section
      aria-label="Ejemplo hipotético de opciones compradas"
      className="flex flex-col gap-4 rounded-2xl border border-gray-800 bg-surface-1 p-5"
    >
      <h2 className="text-lg font-medium text-gray-100">
        Ejemplo hipotético · al vencimiento
      </h2>
      <p className="text-sm text-gray-400">
        Ejercicio $100 · prima $5 por acción · sin comisiones ni impuestos
      </p>
      <svg
        role="img"
        aria-labelledby="payoff-title payoff-desc"
        viewBox="0 0 440 240"
        className="w-full max-w-xl"
      >
        <title id="payoff-title">Resultado de comprar una call o una put</title>
        <desc id="payoff-desc">
          La call pierde $5 si el precio termina en $100 o menos, alcanza
          equilibrio en $105 y gana $15 en $120. La put gana $15 en $80, alcanza
          equilibrio en $95 y pierde $5 en $100 o más. Importes por acción.
        </desc>
        <line x1="50" y1="145" x2="410" y2="145" stroke="#6b7280" />
        <line x1="50" y1="25" x2="50" y2="190" stroke="#6b7280" />
        <g fill="#9ca3af" fontSize="12">
          <text x="8" y="39">
            +$15
          </text>
          <text x="16" y="149">
            $0
          </text>
          <text x="12" y="184">
            -$5
          </text>
          <text x="40" y="208">
            $80
          </text>
          <text x="215" y="208">
            $100
          </text>
          <text x="391" y="208">
            $120
          </text>
          <text x="145" y="231">
            Precio del subyacente
          </text>
        </g>
        <polyline
          points="50,180 230,180 410,35"
          fill="none"
          stroke="#bef264"
          strokeWidth="3"
        />
        <polyline
          points="50,35 230,180 410,180"
          fill="none"
          stroke="#60a5fa"
          strokeWidth="3"
          strokeDasharray="6 4"
        />
        <g fontSize="13">
          <text x="290" y="40" fill="#bef264">
            Call comprada
          </text>
          <text x="65" y="24" fill="#60a5fa">
            Put comprada
          </text>
        </g>
      </svg>
      <p className="text-xs text-gray-500">
        Call: max(precio - ejercicio, 0) - prima. Put: max(ejercicio - precio,
        0) - prima. Antes del vencimiento el precio de la opción también depende
        del tiempo y la volatilidad.
      </p>
    </section>
  );
}
