/** Acota la espera de un enriquecimiento opcional. No cancela su I/O interno. */
export async function withOptionalBudget<T>(work: () => Promise<T>, fallback: T, timeoutMs: number): Promise<T> {
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
        return await Promise.race([
            Promise.resolve().then(work).catch(() => fallback),
            new Promise<T>((resolve) => { timer = setTimeout(() => resolve(fallback), timeoutMs); }),
        ]);
    } finally {
        if (timer !== undefined) clearTimeout(timer);
    }
}
