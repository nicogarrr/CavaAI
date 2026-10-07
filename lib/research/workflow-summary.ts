/** Resúmenes del alcance real de data-engine/app/workflows/catalog.py. */
const SUMMARIES: Record<string, string> = {
    GenerateThesisWorkflow: 'Genera una nueva versión de la tesis con los datos disponibles de una empresa.',
    ThesisShadowComparisonWorkflow: 'Compara el recorrido de investigación con el estado guardado. No publica ni modifica la tesis.',
    ThesisApprovalWorkflow: 'Prepara una revisión y espera una decisión. La aprobación no publica por sí sola una tesis nueva.',
    DailyResearchWorkflow: 'Incorpora las noticias enviadas a la biblioteca. Las otras tareas diarias se ejecutan por separado.',
    EarningsWorkflow: 'Revisa los documentos de resultados de una empresa y registra cambios y métricas.',
    RedTeamWorkflow: 'Comprueba afirmaciones y supuestos de una tesis con reglas sobre la evidencia disponible.',
};

export function workflowSummary(name: string): string {
    return SUMMARIES[name] ?? 'Flujo registrado. Consulta su alcance en los detalles técnicos.';
}
