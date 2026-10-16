/**
 * Utilidades puras de la lectura en voz alta local (WorldStocks punto 6).
 * Sin window ni speechSynthesis: se prueban en node sin DOM.
 */

export interface SpeechVoiceLike {
    lang: string;
    /** false = voz de red (el texto SALE del dispositivo hacia el proveedor). */
    localService: boolean;
}

/**
 * Solo voces en español y LOCALES (localService !== false). Una voz remota
 * manda el texto a un servidor: con ella la promesa «nada sale del
 * dispositivo» sería falsa, así que se rechaza aunque sea la única.
 */
export function pickLocalSpanishVoice<T extends SpeechVoiceLike>(voices: T[]): T | null {
    return (
        voices.find((voice) => voice.lang.toLowerCase().startsWith('es') && voice.localService) ??
        null
    );
}

/**
 * Trocea párrafos para la cola de utterances. Una utterance larga se corta a
 * los ~15 s en Chromium, así que nada supera `maxLen`: se parte por frases y,
 * si una frase sola ya excede, por palabras.
 */
export function speechChunks(paragraphs: string[], maxLen = 220): string[] {
    const chunks: string[] = [];
    for (const paragraph of paragraphs) {
        const sentences = paragraph.match(/[^.!?…]+[.!?…]+["'»)\]]*\s*|[^.!?…]+$/g) ?? [paragraph];
        let buffer = '';
        const flush = () => {
            const trimmed = buffer.trim();
            if (trimmed) chunks.push(trimmed);
            buffer = '';
        };
        for (const raw of sentences) {
            const sentence = raw.trim();
            if (!sentence) continue;
            if (sentence.length > maxLen) {
                flush();
                let rest = sentence;
                while (rest.length > maxLen) {
                    let cut = rest.lastIndexOf(' ', maxLen);
                    if (cut < maxLen * 0.4) cut = maxLen;
                    chunks.push(rest.slice(0, cut).trim());
                    rest = rest.slice(cut).trim();
                }
                buffer = rest;
            } else if ((buffer ? `${buffer} ${sentence}` : sentence).length > maxLen) {
                flush();
                buffer = sentence;
            } else {
                buffer = buffer ? `${buffer} ${sentence}` : sentence;
            }
        }
        flush();
    }
    return chunks;
}
