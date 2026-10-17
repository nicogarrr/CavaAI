type BrainGlassesIconProps = {
  className?: string
}

/**
 * Logo plano del "cerebro" del asistente de cartera (cerebro coral con
 * gafas, diseno multicolor aprobado por Nico). Es un asset estatico con
 * colores propios, no hereda `currentColor`; se sirve desde
 * `public/assets/icons/brain-glasses.svg`.
 */
export function BrainGlassesIcon({ className }: BrainGlassesIconProps) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- icono SVG local estatico; no pasa por el optimizador
    <img src="/assets/icons/brain-glasses.svg" alt="" aria-hidden="true" className={className} />
  )
}
