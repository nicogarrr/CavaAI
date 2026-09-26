/**
 * Mensaje generico por categoria para estados de seccion caidos.
 * El error crudo (rutas internas, detalles de red, fragments de respuesta,
 * URLs firmadas) nunca llega al usuario.
 */
export function sectionError(error: unknown): string {
    const message = error instanceof Error ? error.message : '';
    if (/fetch|network|econn|timeout|timed out|abort/i.test(message)) {
        return 'No se pudo conectar con el servicio. Reintenta en unos segundos.';
    }
    if (/401|403|unauthor|forbidden|sesion|session/i.test(message)) {
        return 'Tu sesion ha caducado. Vuelve a entrar para ver esta seccion.';
    }
    if (/5\d\d|server|interno|internal/i.test(message)) {
        return 'El servicio ha fallado. Reintenta en unos segundos.';
    }
    return 'No se pudieron cargar los datos. Reintenta en unos segundos.';
}
