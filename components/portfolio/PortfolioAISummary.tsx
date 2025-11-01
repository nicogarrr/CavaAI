'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { generatePortfolioSummary } from '@/lib/actions/ai.actions';

export default function PortfolioAISummary({
  portfolio,
  history,
}: {
  portfolio: PortfolioPerformance;
  history: { t: number[]; v: number[] };
}) {
  const [text, setText] = useState<string>('Generando resumen con IA...');

  // Conversor markdown -> HTML muy ligero para títulos, listas y negritas
  const html = useMemo(() => {
    const src = text || '';
    const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const colorizePercents = (s: string) =>
      s.replace(/([+\-]?\d{1,3}(?:[\.,]\d+)?%)/g, (m) => {
        const num = parseFloat(m.replace('%','').replace(',','.'));
        if (isNaN(num)) return m;
        const cls = num >= 0 ? 'text-[#0FEDBE]' : 'text-red-400';
        return `<span class="${cls} font-medium">${m}</span>`;
      });

    const lines = esc(src).split(/\r?\n/);
    const out: string[] = [];
    let inList = false;

    const flushList = () => {
      if (inList) { out.push('</ul>'); inList = false; }
    };

    for (let raw of lines) {
      // Bold **text**
      raw = raw.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      raw = colorizePercents(raw);
      // Headings
      if (/^###\s+/.test(raw)) { flushList(); out.push(`<h3 class="text-lg font-semibold mt-4 mb-2">${raw.replace(/^###\s+/, '')}</h3>`); continue; }
      if (/^##\s+/.test(raw))  { flushList(); out.push(`<h2 class="text-xl font-bold mt-5 mb-3">${raw.replace(/^##\s+/, '')}</h2>`); continue; }
      if (/^#\s+/.test(raw))   { flushList(); out.push(`<h1 class="text-2xl font-bold mt-6 mb-3">${raw.replace(/^#\s+/, '')}</h1>`); continue; }

      // Lists "- " or "* "
      if (/^\s*([*-])\s+/.test(raw)) {
        if (!inList) { out.push('<ul class="list-disc ml-6 space-y-1">'); inList = true; }
        out.push(`<li>${raw.replace(/^\s*([*-])\s+/, '')}</li>`);
        continue;
      } else {
        flushList();
      }

      // Horizontal rule
      if (/^---+$/.test(raw.trim())) { out.push('<hr class="border-gray-800 my-3"/>'); continue; }

      // Paragraph
      const trimmed = raw.trim();
      if (trimmed.length > 0) out.push(`<p class="text-gray-200 leading-6">${trimmed}</p>`);
    }

    flushList();
    return out.join('\n');
  }, [text]);

  useEffect(() => {
    let mounted = true;
    generatePortfolioSummary({ portfolio, history })
      .then((t) => mounted && setText(t))
      .catch(() => mounted && setText('No se pudo generar el resumen.'));
    return () => {
      mounted = false;
    };
  }, [portfolio, history]);

  return (
    <section className="w-full bg-[#0F0F0F] rounded-lg border border-gray-800 p-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-2xl font-semibold">Resumen con IA</h2>
      </div>
      <div className="prose prose-invert max-w-none text-sm" dangerouslySetInnerHTML={{ __html: html }} />
    </section>
  );
}
