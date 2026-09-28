/**
 * Carga por lotes con aislamiento de fallos (índice /research).
 * Un lote que falla NO borra los demás: su hueco queda en null y la
 * página marca solo esas tarjetas como no leídas. Lógica testeable en
 * node (sin imports con alias).
 */

/**
 * Trocea `items` en lotes de `batchSize` y resuelve cada lote con
 * `fetchBatch`. Devuelve un resultado por lote, en orden: el valor del
 * lote o null si ese lote falló (los demás se conservan).
 */
export async function fetchInBatches<T>(
    items: readonly string[],
    batchSize: number,
    fetchBatch: (batch: string[]) => Promise<T>,
): Promise<Array<T | null>> {
    if (batchSize < 1) throw new Error('batchSize debe ser >= 1');
    const batches: string[][] = [];
    for (let index = 0; index < items.length; index += batchSize) {
        batches.push(items.slice(index, index + batchSize));
    }
    return Promise.all(
        batches.map((batch) => fetchBatch(batch).catch(() => null)),
    );
}
