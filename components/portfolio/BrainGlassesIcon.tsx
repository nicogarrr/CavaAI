type BrainGlassesIconProps = {
  className?: string
}

/**
 * Logo plano propio del "cerebro" del asistente de cartera: silueta de
 * cerebro rellena con las gafas talladas en negativo (fill-rule evenodd),
 * dibujado a mano para GerarAI, sin assets de terceros ni licencias.
 * Hereda el color via `currentColor` y se mantiene legible desde 16 px
 * en temas claro y oscuro.
 */
export function BrainGlassesIcon({ className }: BrainGlassesIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      stroke="none"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <g transform="translate(-0.96 -0.92) scale(1.08)">
        <path
          fillRule="evenodd"
          d="M12 3.6c-1.7-1.5-4.4-1.5-5.8 0-2.1-.3-4 1.4-3.8 3.5-1.4.7-1.9 2.6-1 4-.8 1.5.1 3.4 1.9 3.8-.2 2 1.6 3.6 3.7 3.2.9 1.7 3 2.4 4.9 1.5 2 .9 4.1.2 5-1.5 2.1.4 4-1.2 3.7-3.2 1.8-.4 2.7-2.3 1.9-3.8.9-1.4.4-3.3-1-4 .2-2.1-1.7-3.8-3.8-3.5-1.4-1.5-4-1.5-5.7 0zM6.2 10.9a2.3 2.3 0 1 0 4.6 0 2.3 2.3 0 0 0-4.6 0zm7 0a2.3 2.3 0 1 0 4.6 0 2.3 2.3 0 0 0-4.6 0zm-2.5-.55a.55.55 0 0 1 .55-.55h1.6a.55.55 0 0 1 .55.55v1.1a.55.55 0 0 1-.55.55h-1.6a.55.55 0 0 1-.55-.55z"
        />
      </g>
    </svg>
  )
}
