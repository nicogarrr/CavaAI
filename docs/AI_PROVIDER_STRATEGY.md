# AI Provider Strategy

Date: 2026-08-16

## Decision

CavaAI uses **OpenCode (Zen API) as its only LLM provider**. All backend
research workflows use the same OpenAI-compatible API:

```text
https://opencode.ai/zen/v1/chat/completions
```

The default model is `space-bunny-free` (free tier per the official OpenCode
Zen documentation). The model can be changed through `OPENCODE_GO_MODEL`
without adding another provider.

The Go endpoint (`/zen/go/v1`) is documented by OpenCode for code-agent
traffic only (it requires `x-opencode-session` and routing aimed at coding
agents); the general API is Zen (`/zen/v1`). Verified live with the
production key (2026-09-30): `space-bunny-free` answers 200 on Zen with
correct structured extraction; `deepseek-v4-flash` is NOT enabled on Zen
for the account (403 "Model access is disabled").

## Configuration

```env
OPENCODE_GO_API_KEY=replace_with_an_opencode_go_key
OPENCODE_GO_BASE_URL=https://opencode.ai/zen/v1
OPENCODE_GO_MODEL=space-bunny-free
OPENCODE_GO_FALLBACK_MODEL=muse-spark-1.3-contributor-free
OPENCODE_GO_REASONING_EFFORT=max
```

`space-bunny-free` is a reasoning model and accepts the effort levels
`low|medium|high|xhigh|max` (models.dev catalog, verified 2026-09-30).
`OPENCODE_GO_REASONING_EFFORT` (default `max`) is sent as
`reasoning_effort` in the OpenAI-compatible envelope, only to the models
listed in `OPENCODE_GO_REASONING_EFFORT_MODELS` (default
`space-bunny-free`). The fallback `muse-spark-1.3-contributor-free` is
also a reasoning model, but its catalog tops out at `xhigh` (no `max`), so
the default list excludes it and it never receives a level it would
reject. Empty value disables the parameter.

If the resolved model fails at the LLM layer (after its own retries), the
call is retried once with `OPENCODE_GO_FALLBACK_MODEL`
(`muse-spark-1.3-contributor-free`, the free Muse Spark tier on Zen) before
the error propagates. The fallback span is traced with the model and error
class it recovers from. Note: the free Muse Spark plan lets OpenCode use
prompts for training; it is a resilience fallback only, not the default.
An empty `OPENCODE_GO_FALLBACK_MODEL` disables the fallback.

The API key is a secret and must live only in local `.env` files or deployment
secret stores. It must never be committed, placed in `config.yaml`, or exposed
in client-side code.

## Application contract

```text
LLMProvider
- complete
- structured_output
- task model overrides
- provider/model trace metadata
```

The backend uses one OpenAI-compatible adapter with provider name
`opencode-go`. There are no OpenRouter, OpenAI, Anthropic, or Gemini provider
settings in the application configuration.

## Task routing

All task routes default to `space-bunny-free`:

- Extraction
- Classification and news materiality
- Company chat
- Thesis updates
- Deep research
- Red-team review
- Document synthesis
- Tool workflows

If OpenCode Go publishes a different model, configure that model ID through
`OPENCODE_GO_MODEL` or the task override map. A model override is still sent
to OpenCode Go; it never selects another provider.

## Cost and reliability

OpenCode Go applies its own subscription quotas and model limits. CavaAI keeps
request timeout, retry, daily cap, and monthly cap controls in the backend so
expensive workflows remain bounded. Provider failures are surfaced as typed
LLM errors and do not create unsupported financial facts.

See the official model/endpoint list at:

https://opencode.ai/docs/zen/
