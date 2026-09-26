import { expect, test as base } from "@playwright/test";
import type { APIRequestContext, APIResponse } from "@playwright/test";
import { createHash, createHmac, randomUUID } from "node:crypto";

const apiSecret =
  process.env.RESEARCH_AUTH_SECRET ??
  "cavaai-e2e-research-secret-at-least-32-characters";
const apiTenant = "e2e-api-tenant";
const apiUser = "e2e-api-user";
const apiBaseURL = process.env.E2E_API_URL ?? "http://127.0.0.1:8101";

/**
 * Firma ligada al request: cada llamada firma con nonce unico y cubre
 * metodo, ruta (sin query) y sha256 del cuerpo real. Sirve tanto contra un
 * backend leniente como contra uno estricto.
 */
function signedHeaders(
  method: string,
  path: string,
  body: Buffer,
): Record<string, string> {
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const nonce = randomUUID().replaceAll("-", "");
  const bodyHash = createHash("sha256").update(body).digest("hex");
  const signature = createHmac("sha256", apiSecret)
    .update(
      `${apiTenant}:${apiUser}:${timestamp}:${nonce}:${method.toUpperCase()}:${path}:${bodyHash}`,
    )
    .digest("hex");
  return {
    "X-CavaAI-Tenant": apiTenant,
    "X-CavaAI-User": apiUser,
    "X-CavaAI-Timestamp": timestamp,
    "X-CavaAI-Nonce": nonce,
    "X-CavaAI-Method": method.toUpperCase(),
    "X-CavaAI-Path": path,
    "X-CavaAI-Body-Hash": bodyHash,
    "X-CavaAI-Signature": signature,
  };
}

type MultipartValue =
  | string
  | number
  | boolean
  | { name: string; mimeType: string; buffer: Buffer };

function serializeMultipart(fields: Record<string, MultipartValue>): {
  body: Buffer;
  contentType: string;
} {
  const boundary = `----cavaai-e2e-${randomUUID()}`;
  const chunks: Buffer[] = [];
  for (const [name, value] of Object.entries(fields)) {
    if (typeof value === "object" && value !== null && "buffer" in value) {
      chunks.push(
        Buffer.from(
          `--${boundary}\r\nContent-Disposition: form-data; name="${name}"; filename="${value.name}"\r\nContent-Type: ${value.mimeType}\r\n\r\n`,
        ),
        value.buffer,
        Buffer.from("\r\n"),
      );
    } else {
      chunks.push(
        Buffer.from(
          `--${boundary}\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n${String(value)}\r\n`,
        ),
      );
    }
  }
  chunks.push(Buffer.from(`--${boundary}--\r\n`));
  return {
    body: Buffer.concat(chunks) as unknown as Buffer,
    contentType: `multipart/form-data; boundary=${boundary}`,
  };
}

type FetchOptions = NonNullable<Parameters<APIRequestContext["fetch"]>[1]>;

async function signedCall(
  request: APIRequestContext,
  method: string,
  url: string,
  options: FetchOptions,
): Promise<APIResponse> {
  const path = new URL(url, apiBaseURL).pathname;
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  };
  let body: Buffer = Buffer.alloc(0);
  const fetchOptions: FetchOptions = { ...options, method };
  if (options.multipart) {
    const serialized = serializeMultipart(
      options.multipart as Record<string, MultipartValue>,
    );
    body = serialized.body;
    fetchOptions.data = body;
    headers["Content-Type"] = serialized.contentType;
    delete fetchOptions.multipart;
  } else if (options.data !== undefined) {
    body = Buffer.from(JSON.stringify(options.data));
    fetchOptions.data = body;
    headers["Content-Type"] = "application/json";
  }
  fetchOptions.headers = { ...signedHeaders(method, path, body), ...headers };
  return request.fetch(url, fetchOptions);
}

/**
 * Extiende el fixture `request`: cada llamada firma por request con nonce
 * unico, en lugar de la HMAC legacy global que playwright.config.ts inyectaba
 * via extraHTTPHeaders.
 */
export const test = base.extend({
  // El callback se llama `provide` y no `use` para que la regla
  // react-hooks/rules-of-hooks no lo confunda con un hook de React.
  request: async ({ request }, provide) => {
    const verbs = ["get", "post", "put", "delete", "patch", "head", "fetch"];
    const wrapper = new Proxy(request, {
      get(target, prop, receiver) {
        const verb = String(prop);
        if (verbs.includes(verb)) {
          return (url: string, options?: FetchOptions) =>
            signedCall(target, verb === "fetch" ? String(options?.method ?? "GET") : verb, url, options ?? {});
        }
        return Reflect.get(target, prop, receiver);
      },
    });
    await provide(wrapper);
  },
});

export { expect };

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
