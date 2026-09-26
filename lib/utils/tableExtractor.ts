/**
 * Extractor de datos de tablas markdown
 * Extrae datos estructurados de tablas en markdown para generar visualizaciones
 */

import { parseLocalizedNumber } from '@/lib/format';

export interface TableData {
    headers: string[];
    rows: string[][];
    raw: string;
}

/**
 * Extrae datos de una tabla markdown
 */
export function extractTableData(tableMarkdown: string): TableData | null {
    // Validar que tableMarkdown es un string
    if (typeof tableMarkdown !== 'string') {
        console.error('extractTableData: tableMarkdown is not a string', typeof tableMarkdown);
        return null;
    }
    
    const lines = tableMarkdown.trim().split('\n');
    
    if (lines.length < 2) return null;
    
    const headerLine = lines[0].trim();
    const dataLines = lines.slice(2);
    
    // Extraer headers
    const headers = extractColumns(headerLine);
    if (headers.length === 0) return null;
    
    // Extraer filas de datos
    const rows = dataLines
        .filter(line => line.trim().length > 0 && line.includes('|'))
        .map(line => extractColumns(line))
        .filter(row => row.length > 0);
    
    return {
        headers,
        rows,
        raw: tableMarkdown
    };
}

function extractColumns(line: string): string[] {
    const cleaned = line.trim().replace(/^\||\|$/g, '').trim();
    if (!cleaned) return [];
    
    return cleaned.split('|').map(col => col.trim());
}


/**
 * Convierte datos de tabla a formato para gráficos
 */
export function tableToChartData(tableData: TableData, xAxisIndex: number = 0, yAxisIndex: number = 1): Array<{ name: string; value: number }> {
    const chartData: Array<{ name: string; value: number }> = [];
    
    for (const row of tableData.rows) {
        if (row.length <= Math.max(xAxisIndex, yAxisIndex)) continue;
        
        const name = row[xAxisIndex] || '';
        const valueStr = row[yAxisIndex] || '0';
        
        // Extraer número de la cadena (puede tener formato como "18,00%" o "$1.234,56")
        const numericValue = extractNumericValue(valueStr);
        
        if (!isNaN(numericValue) && name) {
            chartData.push({
                name,
                value: numericValue
            });
        }
    }
    
    return chartData;
}

/**
 * Extrae valor numérico de una cadena formateada.
 *
 * Las tablas en markdown las genera el LLM o vienen de un informe, así que
 * aparecen ambos formatos: "$1.234,56" (es-ES) y "$1,234.56" (en-US).
 * `parseLocalizedNumber` cubre los dos (con coma -> decimal español; sin
 * coma -> se parsea tal cual). El parseo anterior quita los puntos SIEMPRE y
 * convertía la primera coma, así que "$1,234.56" acababa en 1.23456.
 */
function extractNumericValue(str: string): number {
    const cleaned = str
        .replace(/[$€£]/g, '') // símbolos de divisa
        .replace(/%/g, '')
        .replace(/\s/g, '');
    return parseLocalizedNumber(cleaned) ?? 0;
}

