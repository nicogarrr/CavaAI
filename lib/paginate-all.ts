/**
 * Pagina un endpoint `limit`/`offset` hasta agotarlo, con salida adversa
 * explícita: si el backend (o un proxy intermedio) ignora `offset`, cada
 * página repite contenido y un bucle «hasta página corta» no terminaría
 * nunca, colgando la petición y acumulando memoria. En cuanto una página
 * no progresa (su primer elemento ya abrió una página anterior) se lanza
 * error: NUNCA se devuelve una lista parcial que la interfaz pudiera
 * rotular como completa.
 */
export async function paginateAll<T>(
    fetchPage: (offset: number) => Promise<T[]>,
    pageSize: number,
    firstKey: (item: T) => string,
): Promise<T[]> {
    const all: T[] = [];
    const seenFirstKeys = new Set<string>();
    for (let offset = 0; ; offset += pageSize) {
        const page = await fetchPage(offset);
        const first = page[0];
        if (first !== undefined) {
            const key = firstKey(first);
            if (seenFirstKeys.has(key)) {
                throw new Error(
                    'paginateAll: el backend no avanza con offset (página repetida); índice incompleto',
                );
            }
            seenFirstKeys.add(key);
        }
        all.push(...page);
        if (page.length < pageSize) return all;
    }
}
