'use client';

import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Pause, Play, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { pickLocalSpanishVoice, speechChunks } from '@/lib/research/speech';

/**
 * Audio básico de la tesis (WorldStocks punto 6): lectura en voz alta con la
 * síntesis del propio navegador (Web Speech API). No hay API nueva ni coste.
 *
 * La promesa «nada sale del dispositivo» solo vale con una voz LOCAL
 * (localService !== false): una voz de red manda el texto al proveedor. Sin
 * voz española local el botón queda deshabilitado y se dice por qué; nunca se
 * cae a la voz por defecto del navegador.
 *
 * El texto se trocea en frases cortas: una utterance larga se corta a los
 * ~15 s en Chromium; una cola de utterances cortas no. Cualquier error de la
 * cola devuelve el control a reposo (nunca se queda «sonando» de mentira).
 */
type SpeechStatus = 'idle' | 'playing' | 'paused';

const EMPTY_VOICES: SpeechSynthesisVoice[] = [];
let cachedVoices: SpeechSynthesisVoice[] = EMPTY_VOICES;

function subscribeVoices(onChange: () => void): () => void {
    if (!('speechSynthesis' in window)) return () => {};
    const synth = window.speechSynthesis;
    const update = () => {
        cachedVoices = synth.getVoices();
        onChange();
    };
    // Carga tardía: en muchos navegadores getVoices() llega vacío hasta el
    // evento voiceschanged.
    update();
    synth.addEventListener('voiceschanged', update);
    return () => synth.removeEventListener('voiceschanged', update);
}

export default function ThesisAudioPlayer({ paragraphs, label }: { paragraphs: string[]; label: string }) {
    const supported = useSyncExternalStore(
        () => () => {},
        () => 'speechSynthesis' in window,
        () => false,
    );
    const voices = useSyncExternalStore(
        subscribeVoices,
        () => cachedVoices,
        () => EMPTY_VOICES,
    );
    const voice = supported ? pickLocalSpanishVoice(voices) : null;
    const [status, setStatus] = useState<SpeechStatus>('idle');
    const queue = useRef<SpeechSynthesisUtterance[]>([]);

    useEffect(() => {
        return () => {
            window.speechSynthesis?.cancel();
        };
    }, []);

    if (!supported || paragraphs.length === 0) return null;

    function stop() {
        window.speechSynthesis.cancel();
        queue.current = [];
        setStatus('idle');
    }

    function play() {
        // Sin voz española local no se habla: caer a la voz por defecto
        // podría ser una voz de red (el texto saldría del dispositivo).
        if (!voice) return;
        if (status === 'paused') {
            window.speechSynthesis.resume();
            setStatus('playing');
            return;
        }
        window.speechSynthesis.cancel();
        const utterances = speechChunks([label, ...paragraphs]).map((text) => {
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = voice.lang;
            utterance.voice = voice;
            utterance.onerror = () => {
                stop();
            };
            return utterance;
        });
        if (utterances.length === 0) return;
        const last = utterances[utterances.length - 1];
        last.onend = () => setStatus('idle');
        queue.current = utterances;
        for (const utterance of utterances) window.speechSynthesis.speak(utterance);
        setStatus('playing');
    }

    function pause() {
        window.speechSynthesis.pause();
        setStatus('paused');
    }

    return (
        <section aria-label="Escuchar la tesis" className="rounded-lg border border-gray-800 p-4">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-400">Escuchar la tesis</h3>
            <p className="mt-1 text-xs text-gray-500">
                Lectura en voz alta con una voz local de tu navegador, en este dispositivo: ningún texto sale de él ni usa servicios nuevos.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
                {status === 'playing' ? (
                    <Button type="button" variant="outline" onClick={pause}>
                        <Pause className="mr-2 h-4 w-4" />Pausar
                    </Button>
                ) : (
                    <Button type="button" variant="outline" onClick={play} disabled={!voice}>
                        <Play className="mr-2 h-4 w-4" />{status === 'paused' ? 'Reanudar' : 'Escuchar'}
                    </Button>
                )}
                {status !== 'idle' ? (
                    <Button type="button" variant="outline" onClick={stop}>
                        <Square className="mr-2 h-4 w-4" />Detener
                    </Button>
                ) : null}
                {!voice ? (
                    <span className="text-xs text-gray-500">Sin voz en español local en este navegador.</span>
                ) : null}
            </div>
        </section>
    );
}
