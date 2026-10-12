// Vista del modo "Análisis" del chat de la biblioteca. Sin imports: se prueba con node --test.

export type AnalysisCitation = {
  chunk_id: number; document_id: number; title: string; author: string | null;
  page_number: number | null; chunk_index: number; quote: string;
  source_url: string | null; publication_date: string | null; document_type: string;
};
export type CitedPoint = { text: string; nombre?: string; citation: AnalysisCitation };
export type LibraryAnalysis = {
  tesis: CitedPoint[];
  error: CitedPoint;
  escenarios: { nombre: string; probabilidad: number; disparador: string }[];
  modelos: CitedPoint[];
  no_se: string[];
  probabilidades: string;
  aviso: string;
};

export const SUGGESTED_QUESTIONS = [
  '¿Cuándo tiene sentido recomprar acciones?',
  '¿Qué es el margen de seguridad?',
  '¿Cómo piensa Munger sobre la inversión de problemas (invertir al revés)?',
  '¿Qué dicen las cartas sobre los fosos competitivos?',
] as const;

function source(c: AnalysisCitation): string {
  return `${c.author ?? 'Autor no registrado'} · ${c.title} · ${c.page_number === null ? 'página no registrada' : `p. ${c.page_number}`}`;
}

/** Texto plano del análisis para copiar: mismas secciones, citas con su origen y el aviso. */
export function analysisToText(a: LibraryAnalysis): string {
  const cited = (p: CitedPoint) => `${p.nombre ? `${p.nombre}: ` : ''}${p.text}\n   «${p.citation.quote}» (${source(p.citation)})`;
  return [
    'Tesis',
    ...a.tesis.map((p, i) => `${i + 1}. ${cited(p)}`),
    '',
    'Qué me haría equivocarme',
    cited(a.error),
    '',
    `Escenarios (${a.probabilidades})`,
    ...a.escenarios.map(s => `- ${s.nombre}: ${s.probabilidad} %. Disparador: ${s.disparador}`),
    '',
    'Modelos mentales',
    ...a.modelos.map(p => `- ${cited(p)}`),
    '',
    'Lo que no sé',
    ...a.no_se.map(t => `- ${t}`),
    '',
    a.aviso,
  ].join('\n');
}

/** Ctrl+Enter o Cmd+Enter envían; Enter solo no. */
export function isSubmitShortcut(e: { key: string; ctrlKey: boolean; metaKey: boolean }): boolean {
  return e.key === 'Enter' && (e.ctrlKey || e.metaKey);
}
