/**
 * Destino de `/` segun el estado de sesion.
 *
 * La raiz es la unica puerta de entrada que un visitante desconocido teclea:
 * sin sesion debe ver la landing publica. Con sesion iniciada, la landing es
 * un paso intermedio sin valor (el propio CTA de cabecera dice "Ir a mi
 * panel"), asi que la raiz redirige directamente al panel.
 */
export function landingTargetForSession(signedIn: boolean): string | null {
    return signedIn ? '/inicio' : null;
}
