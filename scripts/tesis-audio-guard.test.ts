import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
// @ts-expect-error TS5097: la extensión explícita la exige node --experimental-strip-types.
import { pickLocalSpanishVoice, speechChunks } from '../lib/research/speech.ts';

/**
 * Guard del audio básico de tesis (WorldStocks punto 6): lectura local con
 * Web Speech API, SOLO con voz española local (una voz de red mandaría el
 * texto fuera del dispositivo), troceo real por frases y estado que no se
 * queda colgado en "playing" ante un error.
 */
const player = readFileSync('components/research/ThesisAudioPlayer.tsx', 'utf8');
const memo = readFileSync('components/research/ThesisMemo.tsx', 'utf8');

describe('audio de tesis: voz estrictamente local', () => {
    it('elige una voz española local cuando existe', () => {
        const voices = [
            { lang: 'en-US', localService: true },
            { lang: 'es-ES', localService: true },
        ];
        assert.equal(pickLocalSpanishVoice(voices)?.lang, 'es-ES');
    });
    it('canario: solo voz remota -> null (speak no se puede llamar)', () => {
        const remoteOnly = [
            { lang: 'es-ES', localService: false },
            { lang: 'es-MX', localService: false },
        ];
        assert.equal(pickLocalSpanishVoice(remoteOnly), null);
        assert.equal(pickLocalSpanishVoice([]), null);
        // El componente no habla sin voz: ni botón habilitado ni speak.
        assert.match(player, /disabled=\{!voice\}/);
        assert.match(player, /if \(!voice\) return;/);
    });
    it('nunca cae a la voz por defecto del navegador', () => {
        assert.doesNotMatch(player, /voice \?\?|voice \|\|/);
        assert.match(player, /utterance\.voice = voice/);
        // Y las voces se cargan también por carga tardía.
        assert.match(player, /voiceschanged/);
    });
});

describe('audio de tesis: troceo real y estado robusto', () => {
    it('un párrafo largo se trocea por frases y ningún chunk excede el límite', () => {
        const longParagraph = `${'Esta es una frase de prueba con contenido suficiente. '.repeat(12)}Final.`;
        const chunks = speechChunks([longParagraph], 220);
        assert.ok(chunks.length > 3, `esperaba varios chunks, salieron ${chunks.length}`);
        for (const chunk of chunks) assert.ok(chunk.length <= 220, `chunk de ${chunk.length} > 220`);
        assert.equal(chunks.join(' ').replace(/\s+/g, ' '), longParagraph.replace(/\s+/g, ' ').trim());
    });
    it('una frase que excede el límite se parte por palabras sin perder texto', () => {
        const sentence = Array.from({ length: 80 }, (_, i) => `palabra${i}`).join(' ');
        const chunks = speechChunks([sentence], 100);
        assert.ok(chunks.length > 3);
        for (const chunk of chunks) assert.ok(chunk.length <= 100, `chunk de ${chunk.length} > 100`);
        assert.equal(chunks.join(' '), sentence);
    });
    it('un error de la cola no deja el estado colgado en playing', () => {
        assert.match(player, /utterance\.onerror = \(\) => \{\s*stop\(\);?\s*\}/);
        assert.match(player, /last\.onend = \(\) => setStatus\('idle'\)/);
    });
});

describe('audio de tesis: lectura local y honesta', () => {
    it('es componente cliente y usa solo la síntesis del navegador', () => {
        assert.match(player, /'use client'/);
        assert.match(player, /speechSynthesis/);
        assert.doesNotMatch(player, /fetch\(|axios|XMLHttpRequest|MediaRecorder|new Audio\(/);
    });
    it('se cancela la lectura al desmontar (sin audio huérfano)', () => {
        assert.match(player, /return \(\) => \{\s*window\.speechSynthesis\?\.cancel\(\);?\s*\};/);
    });
    it('sin soporte o sin texto no pinta nada (mejora progresiva)', () => {
        assert.match(player, /if \(!supported \|\| paragraphs\.length === 0\) return null;/);
    });
    it('el copy dice voz local en el dispositivo, sin prometer de más', () => {
        assert.match(player, /voz local de tu navegador, en este dispositivo/);
        assert.match(player, /Sin voz en español local en este navegador\./);
    });
    it('la tesis lo monta al final y solo con texto persistido y visible', () => {
        assert.match(memo, /import ThesisAudioPlayer from '@\/components\/research\/ThesisAudioPlayer';/);
        assert.match(memo, /<ThesisAudioPlayer label=\{`Tesis de /);
        assert.ok(memo.indexOf('Memorando completo') < memo.indexOf('<ThesisAudioPlayer'));
        assert.match(memo, /thesis\.executive_summary/);
        assert.match(memo, /thesis\.invalidation_criteria/);
    });
});
