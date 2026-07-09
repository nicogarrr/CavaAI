import { expect, test } from "@playwright/test";
import type { APIResponse } from "@playwright/test";

export { expect, test };

export const E2E_ENABLED = process.env.E2E_RUN === "1";
export const E2E_SKIP_REASON =
  "Set E2E_RUN=1 and provide the data-engine dependencies to run research E2E tests.";

export function uniqueMarker(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export async function jsonResponse<T>(
  response: APIResponse,
  expectedStatus = 200,
): Promise<T> {
  const body = await response.text();
  expect(response.status(), body).toBe(expectedStatus);
  return JSON.parse(body) as T;
}

export function researchEvidencePdf(marker: string): Buffer {
  const evidence =
    `MSFT primary evidence ${marker}: Azure AI demand supports durable cloud revenue growth and disciplined capital expenditure.`;
  const stream = `BT\n/F1 12 Tf\n72 720 Td\n(${escapePdfText(evidence)}) Tj\nET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
  ];

  let pdf = "%PDF-1.4\n";
  const offsets: number[] = [];
  for (const [index, object] of objects.entries()) {
    offsets.push(Buffer.byteLength(pdf));
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
  }

  const xrefOffset = Buffer.byteLength(pdf);
  pdf += `xref\n0 ${objects.length + 1}\n`;
  pdf += "0000000000 65535 f \n";
  pdf += offsets
    .map((offset) => `${offset.toString().padStart(10, "0")} 00000 n \n`)
    .join("");
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\n`;
  pdf += `startxref\n${xrefOffset}\n%%EOF\n`;

  return Buffer.from(pdf);
}

function escapePdfText(value: string): string {
  return value.replaceAll("\\", "\\\\").replaceAll("(", "\\(").replaceAll(")", "\\)");
}
