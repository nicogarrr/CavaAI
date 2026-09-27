/**
 * F300-extensión: destino principal de una tarjeta de alerta del inicio.
 * La tarjeta entera navega (enlace estirado) al destino más útil: la
 * investigación del ticker si lo hay; si no, el documento fuente. Sin
 * ninguno, la tarjeta no es navegable. El CTA secundario queda por encima
 * (z-10) y conserva su propio destino.
 */
export type AlertCardDestination = { href: string; external: boolean };

export function alertCardDestination(item: {
    ticker?: string | null;
    sourceUrl?: string | null;
}): AlertCardDestination | null {
    if (item.ticker) {
        return { href: `/research/${item.ticker}`, external: false };
    }
    if (item.sourceUrl) {
        return { href: item.sourceUrl, external: true };
    }
    return null;
}
