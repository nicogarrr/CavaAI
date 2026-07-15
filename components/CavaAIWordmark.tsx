import { ChartNoAxesCombined } from "lucide-react";

export function CavaAIWordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2" aria-label="CavaAI">
      <span className="grid h-9 w-9 place-items-center rounded-xl border border-teal-300/30 bg-teal-400/10 text-teal-300">
        <ChartNoAxesCombined className="h-5 w-5" aria-hidden="true" />
      </span>
      {!compact && (
        <span className="text-xl font-semibold tracking-tight text-white">
          Cava<span className="text-teal-300">AI</span>
        </span>
      )}
    </span>
  );
}
