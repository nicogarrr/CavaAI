export const DEFAULT_OPENCODE_GO_MODEL = 'deepseek-v4-flash';

export function getOpenCodeGoModel(): string {
  return process.env.OPENCODE_GO_MODEL || DEFAULT_OPENCODE_GO_MODEL;
}

export function getOpenCodeGoBaseUrl(): string {
  return process.env.OPENCODE_GO_BASE_URL || 'https://opencode.ai/zen/go/v1';
}
