/** Solo para shells públicos/auth: sin Cookie no existe sesión de navegador.
 * Cualquier cookie, conocida o no, mantiene la validación completa del servidor.
 * No sustituye requireAuthenticatedUser ni autoriza acceso privado.
 */
export async function readSessionWhenCookies<T>(
  requestHeaders: Pick<Headers, 'get'>,
  readSession: () => Promise<T>,
): Promise<T | null> {
  if (!requestHeaders.get('cookie')?.trim()) return null;
  return readSession();
}
