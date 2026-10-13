/**
 * Huella de IP para el limite por conexion. Solo servidor (usa node:crypto): no
 * importar desde componentes cliente; por eso vive aparte de `access-request.ts`.
 */
import { createHash } from 'node:crypto';

/**
 * Huella de la IP para limitar abusos sin guardar la IP en claro. La sal sale
 * del entorno; sin sal sigue siendo un hash (no reversible a simple vista).
 */
export function hashIp(ip: string, salt: string): string {
    return createHash('sha256').update(`${salt}|${ip.trim()}`).digest('hex').slice(0, 32);
}

/** Primera IP de `x-forwarded-for` (la del cliente); `unknown` si no hay. */
export function clientIp(forwardedFor: string | null | undefined, realIp?: string | null): string {
    const first = (forwardedFor ?? '').split(',')[0]?.trim();
    return first || (realIp ?? '').trim() || 'unknown';
}
