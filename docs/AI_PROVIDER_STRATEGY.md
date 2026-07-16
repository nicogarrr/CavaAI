# AI Provider Strategy

Date: 2026-07-15

## Recommendation

Use the backend `LLMProvider` abstraction and keep provider choice configurable.

Reasons:

- OpenRouter, OpenAI-compatible endpoints, Anthropic and Gemini share one completion/structured-output contract.
- `LLM_PROVIDER=openrouter` is the supported application policy and never silently falls back to another provider.
- OpenAI, Anthropic and Gemini adapters require explicit provider selection plus task-complete `LLM_MODEL_OVERRIDES`; they do not reuse OpenRouter aliases.
- Task-level model overrides decouple extraction, classification, synthesis and red-team workloads.
- Every run retains provider/model/prompt trace metadata; model output cannot create missing facts.

Example configuration:

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
```

## Implemented interface

```text
LLMProvider
- complete
- structured_output
- task model overrides
- provider/model trace metadata
```

## Task Routing

Use model tiers by work type:

- Extraction: cheap model
- Classification: cheap model
- News relevance/materiality: cheap or default model
- Company chat: default model
- Deep research: deep model
- Red-team thesis review: deep model
- Large document synthesis: deep model with caching where available

## Cost Control

- Keep prompts source-aware and short.
- Chunk documents and summarize progressively.
- Cache stable context.
- Use batch/flex modes for offline jobs where supported.
- Record model, prompt version and source set in Langfuse for expensive calls.
