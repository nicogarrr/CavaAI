import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { CHAT_INTENTS, chatIntentHref } from '@/lib/research/chat-intents';

/**
 * Atajos del asistente por intención (WorldStocks punto 4). Solo formulan la
 * pregunta guiada y la lanzan por el MISMO chat con contrato de evidencia:
 * no añaden respuestas nuevas ni texto generado.
 */
export function ChatIntentLinks({ ticker }: { ticker: string }) {
  return (
    <div className="mb-3 flex flex-wrap gap-2">
      {CHAT_INTENTS.map((intent) => (
        <Button asChild variant="outline" key={intent.key}>
          <Link href={chatIntentHref(ticker, intent)}>{intent.label}</Link>
        </Button>
      ))}
    </div>
  );
}
