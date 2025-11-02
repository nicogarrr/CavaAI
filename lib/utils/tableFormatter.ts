/**
 * Reformateador de tablas markdown
 * Detecta y corrige tablas mal formateadas en markdown
 */

import { extractTableData, TableData } from './tableExtractor';

interface TableBlock {
    start: number;
    end: number;
    content: string;
    fixed: string;
}

export function formatMarkdownTable(table: string): string {
    // Validar que table es un string
    if (typeof table !== 'string') {
        console.error('formatMarkdownTable: table is not a string', typeof table);
        return String(table || '');
    }
    
    const lines = table.trim().split('\n');
    
    // Detectar si es una tabla válida
    if (lines.length < 2) return table;
    
    // Separar header del separador y filas
    const headerLine = lines[0].trim();
    const separatorLine = lines[1]?.trim() || '';
    const dataLines = lines.slice(2);
    
    // Validar que tenga pipes
    if (!headerLine.includes('|')) return table;
    
    // Extraer columnas del header
    const headerColumns = extractColumns(headerLine);
    if (headerColumns.length === 0) return table;
    
    // Procesar separador
    const separatorColumns = extractColumns(separatorLine);
    const numColumns = Math.max(headerColumns.length, separatorColumns.length);
    
    // Normalizar header
    const normalizedHeader = formatTableRow(headerColumns, numColumns);
    
    // Crear separador correcto
    const normalizedSeparator = createTableSeparator(numColumns);
    
    // Normalizar filas de datos
    const normalizedRows = dataLines
        .filter(line => line.trim().length > 0 && line.includes('|'))
        .map(line => {
            const columns = extractColumns(line);
            return formatTableRow(columns, numColumns);
        });
    
    // Unir todo
    return [
        normalizedHeader,
        normalizedSeparator,
        ...normalizedRows
    ].join('\n');
}

function extractColumns(line: string): string[] {
    // Eliminar pipes iniciales y finales opcionales
    const cleaned = line.trim().replace(/^\||\|$/g, '').trim();
    
    if (!cleaned) return [];
    
    // Dividir por pipes, manteniendo espacios
    const columns = cleaned.split('|').map(col => col.trim());
    
    return columns.filter(col => col !== '' || columns.length === 1);
}

function formatTableRow(columns: string[], expectedColumns: number): string {
    // Asegurar que tenemos el número correcto de columnas
    const paddedColumns = [...columns];
    while (paddedColumns.length < expectedColumns) {
        paddedColumns.push('');
    }
    
    // Limpiar y formatear cada columna
    const formattedColumns = paddedColumns.slice(0, expectedColumns).map(col => {
        // Limpiar espacios excesivos pero mantener contenido
        const cleaned = col.trim();
        // Asegurar un espacio antes y después
        return ` ${cleaned} `;
    });
    
    return `|${formattedColumns.join('|')}|`;
}

function createTableSeparator(numColumns: number): string {
    const separatorCells = Array(numColumns).fill(':---:');
    return `|${separatorCells.join('|')}|`;
}

/**
 * Encuentra y corrige todas las tablas en un texto markdown
 */
export function fixAllMarkdownTables(content: string): string {
    // Validar que content es un string
    if (typeof content !== 'string') {
        console.error('fixAllMarkdownTables: content is not a string', typeof content);
        return String(content || '');
    }
    
    // Expresión regular para detectar tablas markdown
    // Busca líneas que empiecen con | y tengan al menos 2 filas
    const tableRegex = /(\|.*\|(?:\r?\n\|[:\-| ]+\|(?:\r?\n\|.*\|)+)?)/gm;
    
    let fixedContent = content;
    let offset = 0;
    
    const matches = [...content.matchAll(tableRegex)];
    
    // Procesar cada tabla encontrada
    for (const match of matches) {
        if (!match.index) continue;
        
        const tableStart = match.index;
        const originalTable = match[0];
        
        // Extraer el bloque completo de la tabla
        const tableBlock = extractTableBlock(content, tableStart);
        
        if (tableBlock) {
            const fixedTable = formatMarkdownTable(tableBlock);
            
            // Reemplazar solo si hay cambios
            if (fixedTable !== tableBlock) {
                const beforeFix = content.substring(0, tableBlock.start);
                const afterFix = content.substring(tableBlock.end);
                fixedContent = beforeFix + fixedTable + afterFix;
                break; // Solo corregir la primera tabla por iteración para evitar problemas de índices
            }
        }
    }
    
    // Si no encontramos tablas con regex, intentar un método más agresivo
    if (fixedContent === content) {
        return fixTablesLineByLine(content);
    }
    
    return fixedContent;
}

/**
 * Extrae un bloque completo de tabla desde una posición inicial
 */
function extractTableBlock(content: string, startIndex: number): { start: number; end: number; content: string } | null {
    const lines = content.split('\n');
    let currentLine = 0;
    let charCount = 0;
    
    // Encontrar la línea inicial
    for (let i = 0; i < lines.length; i++) {
        if (charCount <= startIndex && startIndex < charCount + lines[i].length + 1) {
            currentLine = i;
            break;
        }
        charCount += lines[i].length + 1; // +1 por el salto de línea
    }
    
    // Si la línea no empieza con |, no es una tabla
    if (!lines[currentLine]?.trim().startsWith('|')) {
        return null;
    }
    
    // Encontrar el final de la tabla (hasta que encontremos una línea vacía o que no sea parte de la tabla)
    let endLine = currentLine;
    for (let i = currentLine + 1; i < lines.length; i++) {
        const line = lines[i]?.trim();
        if (!line || line.length === 0) {
            break; // Línea vacía termina la tabla
        }
        if (line.startsWith('|') || line.match(/^[\|:-\s]+$/)) {
            endLine = i;
        } else {
            break; // No es parte de la tabla
        }
    }
    
    // Extraer el bloque
    const tableLines = lines.slice(currentLine, endLine + 1);
    const tableContent = tableLines.join('\n');
    
    // Calcular índices reales
    let start = 0;
    for (let i = 0; i < currentLine; i++) {
        start += lines[i].length + 1;
    }
    
    let end = start;
    for (let i = currentLine; i <= endLine; i++) {
        end += lines[i].length + 1;
    }
    
    return { start, end: end - 1, content: tableContent };
}

/**
 * Corrige tablas línea por línea (método más simple y robusto)
 */
function fixTablesLineByLine(content: string): string {
    // Validar que content es un string
    if (typeof content !== 'string') {
        console.error('fixTablesLineByLine: content is not a string', typeof content);
        return String(content || '');
    }
    
    const lines = content.split('\n');
    const fixedLines: string[] = [];
    let inTable = false;
    let tableStart = -1;
    let tableLines: string[] = [];
    
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmed = line.trim();
        
        // Detectar inicio de tabla
        if (trimmed.startsWith('|') && !inTable) {
            inTable = true;
            tableStart = i;
            tableLines = [line];
            continue;
        }
        
        // Si estamos en una tabla
        if (inTable) {
            // Si la línea sigue siendo parte de la tabla (tiene | o es separador)
            if (trimmed.startsWith('|') || trimmed.match(/^[\|:-\s]+$/)) {
                tableLines.push(line);
            } else {
                // Fin de la tabla, procesarla
                const tableContent = tableLines.join('\n');
                const fixedTable = formatMarkdownTable(tableContent);
                fixedLines.push(fixedTable);
                
                // Agregar la línea actual que no es parte de la tabla
                fixedLines.push(line);
                
                // Resetear estado
                inTable = false;
                tableLines = [];
            }
        } else {
            // No estamos en una tabla, agregar línea normalmente
            fixedLines.push(line);
        }
    }
    
    // Si terminamos en una tabla, procesarla
    if (inTable && tableLines.length > 0) {
        const tableContent = tableLines.join('\n');
        const fixedTable = formatMarkdownTable(tableContent);
        fixedLines.push(fixedTable);
    }
    
    return fixedLines.join('\n');
}

/**
 * Encuentra todas las tablas en un texto markdown y devuelve sus datos estructurados
 */
export function findAllTables(content: string): TableData[] {
    // Validar que content es un string
    if (typeof content !== 'string') {
        console.error('findAllTables: content is not a string', typeof content);
        return [];
    }
    
    const tables: TableData[] = [];
    const lines = content.split('\n');
    
    let currentTable: string[] = [];
    let inTable = false;
    
    for (const line of lines) {
        const trimmed = line.trim();
        
        // Detectar inicio de tabla
        if (trimmed.startsWith('|') && !inTable) {
            inTable = true;
            currentTable = [line];
            continue;
        }
        
        // Si estamos en una tabla
        if (inTable) {
            // Si la línea sigue siendo parte de la tabla
            if (trimmed.startsWith('|') || trimmed.match(/^[\|:-\s]+$/)) {
                currentTable.push(line);
            } else {
                // Fin de la tabla, procesarla
                const tableContent = currentTable.join('\n');
                const fixedContent = formatMarkdownTable(tableContent);
                const tableData = extractTableData(fixedContent);
                if (tableData) {
                    tables.push({
                        ...tableData,
                        raw: fixedContent
                    });
                }
                
                inTable = false;
                currentTable = [];
            }
        }
    }
    
    // Si terminamos en una tabla, procesarla
    if (inTable && currentTable.length > 0) {
        const tableContent = currentTable.join('\n');
        const fixedContent = formatMarkdownTable(tableContent);
        const tableData = extractTableData(fixedContent);
        if (tableData) {
            tables.push({
                ...tableData,
                raw: fixedContent
            });
        }
    }
    
    return tables;
}

