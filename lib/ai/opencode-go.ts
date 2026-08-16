import { getOpenCodeGoBaseUrl, getOpenCodeGoModel } from '@/lib/ai/modelConfig';

export async function completeWithOpenCodeGo(prompt: string): Promise<string> {
  const apiKey = process.env.OPENCODE_GO_API_KEY;
  if (!apiKey) {
    throw new Error('OPENCODE_GO_API_KEY is not configured');
  }

  const response = await fetch(`${getOpenCodeGoBaseUrl().replace(/\/$/, '')}/chat/completions`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: getOpenCodeGoModel(),
      messages: [{ role: 'user', content: prompt }],
      temperature: 0.2,
    }),
    cache: 'no-store',
  });

  if (!response.ok) {
    throw new Error(`OpenCode Go request failed with status ${response.status}`);
  }

  const payload = await response.json() as {
    choices?: Array<{ message?: { content?: string | null } }>;
  };
  const content = payload.choices?.[0]?.message?.content;
  if (!content) {
    throw new Error('OpenCode Go returned an empty response');
  }
  return content;
}
