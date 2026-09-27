import type { FinnhubProfile2 } from '@/lib/actions/finnhub.actions';

/**
 * F286: identidad de un ticker sin research y sin NINGUNA identidad de
 * mercado (fuera del master: quoteSymbolFor devuelve null por el diseño
 * anti-homónimos y el snapshot llega vacío sin haber consultado al
 * proveedor).
 *
 * Política de veracidad: ninguna respuesta del proveedor prueba la
 * INEXISTENCIA del emisor que el usuario busca (un perfil `{}` solo dice que
 * Finnhub no conoce ese símbolo), y un perfil con nombre prueba que el
 * símbolo existe en alguna bolsa, no que sea ese emisor (ALM pelado es
 * Almonty US, no Almirall/BME). Por eso este camino NUNCA devuelve 404 y
 * NUNCA ofrece el CTA «Generar tesis»: tres estados honestos sin CTA.
 *
 * El fallback completo (panel de mercado + CTA) queda reservado a empresas
 * del master, cuya identidad de listado sí está verificada. El perfil del
 * proveedor se usa SOLO como evidencia de existencia: nunca alimenta
 * precio, nombre ni histórico de la ficha.
 */
export type UnknownListingIdentity =
    /** El proveedor no conoce el símbolo (perfil vacío o sin nombre propio). */
    | { kind: 'not-in-sources' }
    /** El símbolo existe en alguna bolsa, pero el emisor no está verificado. */
    | { kind: 'unverified'; providerName: string }
    /** Proveedor no disponible: no se puede comprobar nada. */
    | { kind: 'unavailable' };

export function resolveUnknownListingIdentity(
    profile: FinnhubProfile2 | null,
    ticker: string,
): UnknownListingIdentity {
    if (profile === null) {
        return { kind: 'unavailable' };
    }
    const name = profile.name?.trim();
    if (!name || name.toUpperCase() === ticker.trim().toUpperCase()) {
        return { kind: 'not-in-sources' };
    }
    return { kind: 'unverified', providerName: name };
}
