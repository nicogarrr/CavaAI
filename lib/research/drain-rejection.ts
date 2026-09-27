/**
 * Caveat del auditor (#508/#518): una promesa lanzada en paralelo que quizá
 * nadie consuma (master-miss en /research/[ticker]) no puede quedarse sin
 * manejador de rechazo: Node emite unhandledRejection en cuanto rechaza sin
 * handler, aunque el .catch se adjunte más tarde. Adjuntarlo en creación no
 * cambia la propagación: el consumidor que haga await sigue recibiendo el
 * error por la cadena original (catch devuelve una promesa NUEVA que aquí se
 * descarta).
 */
export function drainRejection<T>(promise: Promise<T> | undefined): void {
    void promise?.catch(() => null);
}
