/** "1 nueva" / "2 nuevas": concordancia de la etiqueta de posiciones nuevas. Sin imports: se testea en node. */
export function newLabel(count: number): string {
    const text = count.toLocaleString('es-ES', { maximumFractionDigits: 0 });
    return `${text} ${count === 1 ? 'nueva' : 'nuevas'}`;
}
