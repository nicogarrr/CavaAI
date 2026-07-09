# AI Provider Strategy

Date: 2026-07-09

## Recommendation

Use Gemini directly for the current product phase.

Reasons:

- The app already uses Google Gemini endpoints.
- Gemini has very low-cost models suitable for extraction, classification, summarization and routing.
- The model can be configured through environment variables without code changes.
- Direct provider integration is simpler while the product core is still stabilizing.

Recommended defaults:

```env
GEMINI_MODEL=gemini-3.5-flash
GEMINI_CHEAP_MODEL=gemini-2.5-flash-lite
GEMINI_DEEP_MODEL=gemini-3.5-flash
```

## OpenRouter

OpenRouter should be the next abstraction target, not the first dependency. It is useful for:

- fallback routing;
- testing multiple models without rewriting code;
- separating dev/staging/prod keys;
- putting spend caps on model experiments.

Add it once CavaAI has a provider interface like:

```text
LLMProvider
- generateText
- generateJson
- extractDocument
- classify
- embed
- modelForTask(task)
- trace metadata
```

## Muse Spark

Do not build the production app around Muse Spark yet.

Muse Spark is promising, but API access/pricing/provider coverage is not stable enough as the primary provider choice. Treat it as an experiment once Meta publishes mature developer docs, pricing, rate limits and an integration surface that can be used outside Meta products.

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
