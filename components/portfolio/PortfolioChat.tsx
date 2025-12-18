'use client';

import { useState, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Brain, MessageSquare, X, Send, User, Bot, Loader2 } from 'lucide-react';
import { chatWithPortfolio } from '@/lib/actions/chat.actions';

interface Message {
    role: 'user' | 'assistant';
    content: string;
}

interface PortfolioChatProps {
    userId: string;
}

export function PortfolioChat({ userId }: PortfolioChatProps) {
    const [isOpen, setIsOpen] = useState(false);
    const [messages, setMessages] = useState<Message[]>([
        { role: 'assistant', content: '¡Hola! Soy CavaAI. Pregúntame sobre tu cartera, tus tesis de inversión o conceptos de Value Investing.' }
    ]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const scrollRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
        }
    }, [messages, isOpen]);

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
                setMessages(prev => [...prev, { role: 'assistant', content: "Lo siento, hubo un error. Inténtalo de nuevo." }]);
            }
        } catch (error) {
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
                className="fixed bottom-6 right-6 h-14 w-14 rounded-full shadow-xl bg-indigo-600 hover:bg-indigo-500 text-white z-50 animate-in zoom-in duration-300"
            >
                <Brain className="h-8 w-8" />
            </Button>
        );
    }

    // Chat Window
    return (
        <Card className="fixed bottom-6 right-6 w-[350px] md:w-[400px] h-[500px] shadow-2xl z-50 flex flex-col border-indigo-500/30 bg-slate-950/95 backdrop-blur-md">
            <CardHeader className="p-4 border-b border-indigo-500/20 flex flex-row items-center justify-between bg-indigo-900/20">
                <div className="flex items-center gap-2">
                    <div className="p-2 bg-indigo-500/20 rounded-full">
                        <Brain className="h-4 w-4 text-indigo-400" />
                    </div>
                    <CardTitle className="text-sm font-medium">CavaAI Assistant</CardTitle>
                </div>
                <Button variant="ghost" size="icon" onClick={() => setIsOpen(false)} className="h-6 w-6 text-slate-400 hover:text-white">
                    <X className="h-4 w-4" />
                </Button>
            </CardHeader>

            <CardContent className="flex-1 p-0 overflow-hidden relative">
                <div ref={scrollRef} className="h-full overflow-y-auto p-4 space-y-4">
                    {messages.map((m, i) => (
                        <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                            <div className={`flex items-start gap-2 max-w-[80%] ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
                                <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 ${m.role === 'user' ? 'bg-blue-600' : 'bg-indigo-600'}`}>
                                    {m.role === 'user' ? <User className="h-3 w-3 text-white" /> : <Bot className="h-3 w-3 text-white" />}
                                </div>
                                <div className={`p-3 rounded-lg text-sm ${m.role === 'user'
                                        ? 'bg-blue-600 text-white rounded-tr-none'
                                        : 'bg-slate-800 text-slate-200 border border-slate-700 rounded-tl-none'
                                    }`}>
                                    {m.content}
                                </div>
                            </div>
                        </div>
                    ))}
                    {loading && (
                        <div className="flex justify-start">
                            <div className="flex items-start gap-2 max-w-[80%]">
                                <div className="w-6 h-6 rounded-full bg-indigo-600 flex items-center justify-center shrink-0">
                                    <Bot className="h-3 w-3 text-white" />
                                </div>
                                <div className="p-3 rounded-lg bg-slate-800 border border-slate-700 rounded-tl-none">
                                    <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
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
                    <Input
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder="Pregunta sobre tu cartera..."
                        className="bg-slate-950 border-slate-700 focus-visible:ring-indigo-500"
                    />
                    <Button type="submit" size="icon" disabled={loading || !input.trim()} className="bg-indigo-600 hover:bg-indigo-500">
                        <Send className="h-4 w-4" />
                    </Button>
                </form>
            </CardFooter>
        </Card>
    );
}
