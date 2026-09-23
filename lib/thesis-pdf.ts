/**
 * Generador mínimo de PDF (sin dependencias) para la exportación de tesis.
 *
 * Produce un PDF 1.4 válido con tipografía Helvetica (WinAnsiEncoding, que
 * cubre los acentos españoles) a partir de líneas de texto ya separadas por
 * el llamador. La paginación y el ajuste de línea son deterministas: mismo
 * memo -> mismo PDF.
 */

export interface PdfLine {
  text: string;
  /** Tamaño de fuente en pt (por defecto 10) */
  size?: number;
  bold?: boolean;
  /** Sangría izquierda en pt */
  indent?: number;
  /** Espacio extra antes de la línea en pt */
  gapBefore?: number;
}

const PAGE_WIDTH = 595; // A4 en pt
const PAGE_HEIGHT = 842;
const MARGIN_X = 56;
const MARGIN_TOP = 56;
const MARGIN_BOTTOM = 56;

/** WinAnsiEncoding cubre Latin-1; lo demás degrada a '?'. */
function toWinAnsi(text: string): string {
  let out = '';
  for (const ch of text) {
    const code = ch.codePointAt(0) ?? 63;
    out += code >= 32 && code <= 255 ? ch : '?';
  }
  return out;
}

function escapePdfText(text: string): string {
  return toWinAnsi(text)
    .replace(/\\/g, '\\\\')
    .replace(/\(/g, '\\(')
    .replace(/\)/g, '\\)');
}

/** Ajuste de línea determinista por ancho aproximado (Helvetica ~0.5·size). */
function wrapText(text: string, size: number, indent: number): string[] {
  const maxWidth = PAGE_WIDTH - MARGIN_X * 2 - indent;
  const approxChars = Math.max(24, Math.floor(maxWidth / (size * 0.5)));
  const words = text.split(/\s+/).filter(Boolean);
  if (words.length === 0) return [''];
  const lines: string[] = [];
  let current = '';
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length > approxChars && current) {
      lines.push(current);
      current = word;
    } else {
      current = candidate;
    }
  }
  if (current) lines.push(current);
  return lines;
}

interface PositionedLine {
  text: string;
  x: number;
  y: number;
  size: number;
  bold: boolean;
}

function layoutLines(lines: PdfLine[]): PositionedLine[][] {
  const pages: PositionedLine[][] = [];
  let page: PositionedLine[] = [];
  let y = PAGE_HEIGHT - MARGIN_TOP;

  const newPage = () => {
    if (page.length) pages.push(page);
    page = [];
    y = PAGE_HEIGHT - MARGIN_TOP;
  };

  for (const line of lines) {
    const size = line.size ?? 10;
    const indent = line.indent ?? 0;
    const x = MARGIN_X + indent;
    const wrapped = wrapText(line.text, size, indent);
    for (let i = 0; i < wrapped.length; i += 1) {
      const gap = i === 0 ? line.gapBefore ?? 0 : 0;
      y -= gap;
      const lineHeight = size * 1.45;
      if (y - lineHeight < MARGIN_BOTTOM) newPage();
      y -= lineHeight;
      page.push({ text: wrapped[i], x, y, size, bold: Boolean(line.bold) });
    }
  }
  newPage();
  return pages;
}

function latin1Bytes(text: string): Uint8Array {
  const out = new Uint8Array(text.length);
  for (let i = 0; i < text.length; i += 1) out[i] = text.charCodeAt(i) & 0xff;
  return out;
}

function contentStream(pageLines: PositionedLine[]): string {
  return pageLines
    .map(
      (line) =>
        `BT /${line.bold ? 'F2' : 'F1'} ${line.size} Tf ${line.x} ${Math.round(line.y)} Td (${escapePdfText(line.text)}) Tj ET`,
    )
    .join('\n');
}

/** Construye un PDF completo (bytes) a partir de un título y líneas de contenido. */
export function buildSimplePdf(title: string, lines: PdfLine[]): Uint8Array {
  const allLines: PdfLine[] = [
    { text: title, size: 18, bold: true, gapBefore: 0 },
    { text: '', size: 10, gapBefore: 6 },
    ...lines,
  ];
  const pages = layoutLines(allLines);

  const objects: string[] = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '', // placeholder de Pages (se rellena con el recuento real)
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>',
  ];

  const pageObjectIds: number[] = [];
  for (let i = 0; i < pages.length; i += 1) {
    const pageObjId = 5 + i * 2;
    const contentObjId = pageObjId + 1;
    pageObjectIds.push(pageObjId);
    const stream = contentStream(pages[i]);
    objects.push(
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PAGE_WIDTH} ${PAGE_HEIGHT}] ` +
        `/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents ${contentObjId} 0 R >>`,
    );
    objects.push(`<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
  }
  objects[1] = `<< /Type /Pages /Kids [${pageObjectIds.map((id) => `${id} 0 R`).join(' ')}] /Count ${pages.length} >>`;

  const chunks: Uint8Array[] = [];
  let offset = 0;
  const offsets: number[] = [];
  const push = (text: string) => {
    const bytes = latin1Bytes(text);
    chunks.push(bytes);
    offset += bytes.length;
  };

  push('%PDF-1.4\n%\u00e2\u00e3\u00cf\u00d3\n');
  for (let i = 0; i < objects.length; i += 1) {
    offsets.push(offset);
    push(`${i + 1} 0 obj\n${objects[i]}\nendobj\n`);
  }
  const xrefOffset = offset;
  push(`xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`);
  for (const objOffset of offsets) {
    push(`${String(objOffset).padStart(10, '0')} 00000 n \n`);
  }
  push(`trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`);

  const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const out = new Uint8Array(total);
  let pos = 0;
  for (const chunk of chunks) {
    out.set(chunk, pos);
    pos += chunk.length;
  }
  return out;
}

/** Convierte Markdown de memo de tesis en líneas de PDF. */
export function memoMarkdownToPdfLines(memo: string): PdfLine[] {
  const stripInline = (text: string) =>
    text
      .replace(/\*\*(.+?)\*\*/g, '$1')
      .replace(/__(.+?)__/g, '$1')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/\*([^*]+)\*/g, '$1');

  const out: PdfLine[] = [];
  for (const raw of memo.split(/\r?\n/)) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      out.push({ text: '', size: 8, gapBefore: 4 });
    } else if (line.startsWith('### ')) {
      out.push({ text: stripInline(line.slice(4)), size: 12, bold: true, gapBefore: 12 });
    } else if (line.startsWith('## ')) {
      out.push({ text: stripInline(line.slice(3)), size: 14, bold: true, gapBefore: 14 });
    } else if (line.startsWith('# ')) {
      out.push({ text: stripInline(line.slice(2)), size: 16, bold: true, gapBefore: 12 });
    } else if (/^[-*]\s+/.test(line)) {
      out.push({ text: `• ${stripInline(line.replace(/^[-*]\s+/, ''))}`, size: 10, indent: 10 });
    } else if (line.startsWith('>')) {
      out.push({ text: stripInline(line.replace(/^>\s?/, '')), size: 10, indent: 14 });
    } else if (line.startsWith('|')) {
      const cells = line
        .split('|')
        .map((cell) => cell.trim())
        .filter(Boolean);
      if (cells.some((cell) => /^-+$/.test(cell))) continue;
      out.push({ text: stripInline(cells.join('  ·  ')), size: 9, indent: 6 });
    } else {
      out.push({ text: stripInline(line), size: 10 });
    }
  }
  return out;
}
