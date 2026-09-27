'use client';

import { useState, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Brain, X, Send, User, Bot, Loader2, Maximize2, Minimize2 } from 'lucide-react';
import { chatWithPortfolio } from '@/lib/actions/chat.actions';
import ReactMarkdown from 'react-markdown';

interface Message {
    role: 'user' | 'assistant';
    content: string;
}

interface PortfolioChatProps {
    userId: string;
}

export function PortfolioChat({ userId }: PortfolioChatProps) {
    const [isOpen, setIsOpen] = useState(false);
    const [isMaximized, setIsMaximized] = useState(false); // State for maximize
    const [messages, setMessages] = useState<Message[]>([
        { role: 'assistant', content: '¡Hola! Soy CavaAI. Pregúntame sobre tu cartera, tus tesis de inversión o conceptos de Value Investing.' }
    ]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const scrollRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
        }
    }, [messages, isOpen, isMaximized]);

    /**
     * Modal de verdad (WCAG 2.1.2): con `aria-modal` el fondo se marca inaccesible
     * para el lector de pantalla, el foco entra por el campo de mensaje y Escape
     * cierra sin enviar nada. El listener va en `document` porque el panel no
     * recibe el foco por si solo.
     */
    useEffect(() => {
        if (!isOpen) return;
        inputRef.current?.focus();

        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key !== 'Escape') return;
            event.preventDefault();
            setIsOpen(false);
        };
        document.addEventListener('keydown', onKeyDown);
        return () => document.removeEventListener('keydown', onKeyDown);
    }, [isOpen]);

    async function handleSend() {
        if (!input.trim() || loading) return;

        const userMsg = input.trim();
        setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
        setInput('');
        setLoading(true);

        try {
            const result = await chatWithPortfolio(userMsg, userId);
            if (result.success) {
                setMessages(prev => [...prev, { role: 'assistant', content: result.message }]);
            } else {
                setMessages(prev => [...prev, { role: 'assistant', content: result.message || "Lo siento, hubo un error desconocido." }]);
            }
        } catch {
            setMessages(prev => [...prev, { role: 'assistant', content: "Error de conexión." }]);
        } finally {
            setLoading(false);
        }
    }

    // Floating Bubble
    if (!isOpen) {
        return (
            <Button
                onClick={() => setIsOpen(true)}
                aria-label="Abrir asistente de cartera"
                // `viewportFit: "cover"` + barra de inicio de iOS: sin el inset la
                // burbuja queda bajo la barra en modo standalone.
                className="fixed bottom-[calc(1.5rem+env(safe-area-inset-bottom))] right-[calc(1.5rem+env(safe-area-inset-right))] h-14 w-14 rounded-full shadow-xl bg-indigo-600 hover:bg-indigo-500 text-white z-50 animate-in zoom-in duration-300"
            >
                <Brain aria-hidden="true" className="h-8 w-8" />
            </Button>
        );
    }

    // Chat Window
    return (
        <Card
            role="dialog"
            aria-modal="true"
            aria-labelledby="portfolio-chat-title"
            aria-busy={loading}
            className={`fixed z-50 flex flex-col border-indigo-500/30 bg-slate-950/95 backdrop-blur-md shadow-2xl transition-all duration-300 ${isMaximized
            ? 'top-4 bottom-4 left-4 right-4 w-auto h-auto'
            : 'bottom-6 right-6 w-[350px] md:w-[450px] h-[600px]'
            }`}
        >
            <CardHeader className="p-4 border-b border-indigo-500/20 flex flex-row items-center justify-between bg-indigo-900/20 cursor-move">
                <div className="flex items-center gap-2">
                    <div className="p-2 bg-indigo-500/20 rounded-full">
                        <Brain aria-hidden="true" className="h-4 w-4 text-indigo-400" />
                    </div>
                    <CardTitle id="portfolio-chat-title" className="text-sm font-medium">CavaAI Assistant</CardTitle>
                </div>
                <div className="flex items-center gap-1">
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setIsMaximized(!isMaximized)}
                        aria-label={isMaximized ? 'Restaurar asistente de cartera' : 'Maximizar asistente de cartera'}
                        className="h-6 w-6 text-slate-400 hover:text-white"
                    >
                        {isMaximized ? <Minimize2 aria-hidden="true" className="h-4 w-4" /> : <Maximize2 aria-hidden="true" className="h-4 w-4" />}
                    </Button>
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setIsOpen(false)}
                        aria-label="Cerrar asistente de cartera"
                        className="h-6 w-6 text-slate-400 hover:text-white"
                    >
                        <X aria-hidden="true" className="h-4 w-4" />
                    </Button>
                </div>
            </CardHeader>

            <CardContent className="flex-1 p-0 overflow-hidden relative">
                <div
                    ref={scrollRef}
                    role="log"
                    aria-live="polite"
                    aria-relevant="additions text"
                    aria-label="Mensajes del asistente de cartera"
                    className="h-full overflow-y-auto p-4 space-y-4"
                >
                    {messages.map((m, i) => (
                        <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                            <div className={`flex items-start gap-2 max-w-[90%] ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
                                <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 ${m.role === 'user' ? 'bg-blue-600' : 'bg-indigo-600'}`}>
                                    {m.role === 'user' ? <User aria-hidden="true" className="h-3 w-3 text-white" /> : <Bot aria-hidden="true" className="h-3 w-3 text-white" />}
                                </div>
                                <div className={`p-3 rounded-lg text-sm overflow-hidden ${m.role === 'user'
                                    ? 'bg-blue-600 text-white rounded-tr-none'
                                    : 'bg-slate-800 text-slate-200 border border-slate-700 rounded-tl-none'
                                    }`}>
                                    {m.role === 'assistant' ? (
                                        <div className="prose prose-invert prose-sm max-w-none [&>h3]:text-indigo-400 [&>h3]:font-bold [&>h3]:mt-2 [&>h3]:mb-1 [&>ul]:list-disc [&>ul]:pl-4 [&>strong]:text-white">
                                            <ReactMarkdown
                                                components={{
                                                    h3: ({ node, ...props }) => <h3 className="text-base font-bold text-indigo-300 mt-2 mb-1" {...props} />,
                                                    ul: ({ node, ...props }) => <ul className="list-disc pl-4 space-y-1" {...props} />,
                                                    li: ({ node, ...props }) => <li className="text-slate-300" {...props} />,
                                                    strong: ({ node, ...props }) => <strong className="font-semibold text-white bg-indigo-500/10 px-1 rounded" {...props} />
                                                }}
                                            >
                                                {m.content}
                                            </ReactMarkdown>
                                        </div>
                                    ) : (
                                        m.content
                                    )}
                                </div>
                            </div>
                        </div>
                    ))}
                    {loading && (
                        <div className="flex justify-start">
                            <div className="flex items-start gap-2 max-w-[80%]">
                                <div className="w-6 h-6 rounded-full bg-indigo-600 flex items-center justify-center shrink-0">
                                    <Bot aria-hidden="true" className="h-3 w-3 text-white" />
                                </div>
                                <div role="status" aria-live="polite" className="p-3 rounded-lg bg-slate-800 border border-slate-700 rounded-tl-none">
                                    <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin text-indigo-400" />
                                    <span className="sr-only">CavaAI está escribiendo la respuesta.</span>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </CardContent>

            <CardFooter className="p-3 border-t border-slate-800 bg-slate-900/50">
                <form
                    className="flex w-full gap-2"
                    onSubmit={(e) => { e.preventDefault(); handleSend(); }}
                >
                    <label htmlFor="portfolio-chat-input" className="sr-only">
                        Pregunta sobre tu cartera
                    </label>
                    <Input
                        ref={inputRef}
                        id="portfolio-chat-input"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder="Pregunta sobre tu cartera..."
                        className="bg-slate-950 border-slate-700 focus-visible:ring-indigo-500"
                    />
                    <Button type="submit" size="icon" aria-label="Enviar pregunta" disabled={loading || !input.trim()} aria-busy={loading} className="bg-indigo-600 hover:bg-indigo-500">
                        <Send aria-hidden="true" className="h-4 w-4" />
                    </Button>
                </form>
            </CardFooter>
        </Card>
    );
}
