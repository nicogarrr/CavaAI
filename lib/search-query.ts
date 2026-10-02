/**
 * Consulta del buscador de acciones sin diacríticos.
 *
 * El proveedor (Finnhub /search) indexa nombres sin acentos: «Telefónica»
 * no devolvía nada y «Telefonica» sí. Se pliega a NFD y se quitan las marcas
 * combinantes antes de enviar la consulta. Solo cambia la forma de escribir:
 * no añade ni inventa ningún dato.
 */
export function foldSearchQuery(query: string): string {
    return query.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/\s+/g, ' ').trim();
}
