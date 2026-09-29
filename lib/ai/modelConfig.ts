export const DEFAULT_OPENCODE_GO_MODEL = 'space-bunny-free';

export function getOpenCodeGoModel(): string {
  return process.env.OPENCODE_GO_MODEL || DEFAULT_OPENCODE_GO_MODEL;
}

export function getOpenCodeGoBaseUrl(): string {
  return process.env.OPENCODE_GO_BASE_URL || 'https://opencode.ai/zen/v1';
}
