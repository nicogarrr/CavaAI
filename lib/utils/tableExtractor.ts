/**
 * Extractor de datos de tablas markdown
 * Extrae datos estructurados de tablas en markdown para generar visualizaciones
 */

export interface TableData {
    headers: string[];
    rows: string[][];
    raw: string;
}

/**
 * Extrae datos de una tabla markdown
 */
export function extractTableData(tableMarkdown: string): TableData | null {
    const lines = tableMarkdown.trim().split('\n');
    
    if (lines.length < 2) return null;
    
    const headerLine = lines[0].trim();
    const separatorLine = lines[1]?.trim() || '';
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
 * Extrae valor numérico de una cadena formateada
 */
function extractNumericValue(str: string): number {
    // Eliminar símbolos comunes y espacios
    let cleaned = str
        .replace(/[$€£]/g, '')
        .replace(/%/g, '')
        .replace(/\s/g, '')
        .replace(/\./g, '') // Eliminar separadores de miles
        .replace(',', '.') // Convertir coma decimal a punto
        .trim();
    
    // Intentar parsear
    const value = parseFloat(cleaned);
    return isNaN(value) ? 0 : value;
}

