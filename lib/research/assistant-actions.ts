'use server';
import { askResearchAssistant, getGuideContext } from '@/lib/research/assistant-client';
import type { AssistantRequest } from '@/lib/research/assistant-contract';

export async function askResearchAssistantAction(request: AssistantRequest) {
  return askResearchAssistant(request);
}
export async function getGuideContextAction(ticker: string) {
  return getGuideContext(ticker);
}
