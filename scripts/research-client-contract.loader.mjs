/**
 * Loader mínimo para el contrato de research client.
 *
 * Node no resuelve el alias @/ ni debe arrancar next/cache. El loader mantiene
 * el código de producción bajo prueba y sustituye sólo dependencias de runtime
 * externas por stubs deterministas.
 */
export async function resolve(specifier, context, nextResolve) {
  const map = new Map([
    ['@/lib/auth/require-user', 'guard-stub:require-user'],
    ['@/lib/auth/research-identity', 'guard-stub:research-identity'],
    ['@/lib/types/errors', new URL('../lib/types/errors.ts', import.meta.url).href],
    ['@/lib/research/client', new URL('../lib/research/client.ts', import.meta.url).href],
    ['@/lib/research/openapi-client', 'guard-stub:openapi-client'],
    ['next/cache', 'guard-stub:next-cache'],
  ]);
  const mapped = map.get(specifier);
  if (mapped) return { url: mapped, shortCircuit: true };
  return nextResolve(specifier, context);
}

export async function load(url, context, nextLoad) {
  if (url === 'guard-stub:require-user') {
    return {
      format: 'module',
      source: [
        'export async function requireAuthenticatedUser() {',
        "  return { id: 'contract-test-user', email: 'contract@test', name: 'Contract' };",
        '}',
      ].join('\n'),
      shortCircuit: true,
    };
  }
  if (url === 'guard-stub:research-identity') {
    return {
      format: 'module',
      source: [
        'export async function normalizeResearchBody(body) {',
        "  return typeof body === 'string' ? { body } : {};",
        '}',
        'export async function researchIdentityHeaders() {',
        "  return { 'X-CavaAI-User': 'contract-test-user' };",
        '}',
      ].join('\n'),
      shortCircuit: true,
    };
  }
  if (url === 'guard-stub:openapi-client') {
    return {
      format: 'module',
      source: [
        'export function createResearchOpenApiClient() {',
        '  return { GET: async () => ({ data: null, error: null, response: { status: 200 } }) };',
        '}',
      ].join('\n'),
      shortCircuit: true,
    };
  }
  if (url === 'guard-stub:next-cache') {
    return {
      format: 'module',
      source: ['export function revalidatePath() {}'].join('\n'),
      shortCircuit: true,
    };
  }
  return nextLoad(url, context);
}
