# AI Provider Strategy

Date: 2026-08-16 (updated 2026-10-17)

## Decision

GerarAI uses **OpenCode (Zen API) as its primary LLM provider**. All backend
research workflows use the same OpenAI-compatible API:

```text
https://opencode.ai/zen/v1/chat/completions
```

The default model is `deepseek-v4.1-flash-free` (free tier), with
`space-bunny-free` as the automatic one-shot fallback
(`OPENCODE_GO_FALLBACK_MODEL`). The model can be changed through
`OPENCODE_GO_MODEL` without adding another provider.

The Go endpoint (`/zen/go/v1`) is documented by OpenCode for code-agent
traffic only (it requires `x-opencode-session` and routing aimed at coding
agents); the general API is Zen (`/zen/v1`).

### 2026-10-16: production goes through the local bridge

The Zen free tier (space-bunny included) refuses direct API calls with
403 `FreeTierError`; free models only answer a real OpenCode client.
Production therefore points `OPENCODE_GO_BASE_URL` at the local bridge
(`data-engine/bridge/opencode_bridge.py`, listening on :4098), which
translates the OpenAI-shaped `POST /v1/chat/completions` into the
session/message API of the jailed `opencode serve` (`oc-serve2`). Verified
with real generation on the VM the same day: `deepseek-v4.1-flash-free` as
principal and `space-bunny-free` as backup, both at zero cost. The bridge is
declared limited: no streaming, no tools/function calling (400 on `tools`),
`response_format json_schema` translated to a prompt instruction, and no own
auth (internal docker network only).

## Configuration

```env
OPENCODE_GO_API_KEY=replace_with_an_opencode_go_key
OPENCODE_GO_BASE_URL=https://opencode.ai/zen/v1   # prod: local bridge URL
OPENCODE_GO_MODEL=deepseek-v4.1-flash-free
OPENCODE_GO_FALLBACK_MODEL=space-bunny-free
OPENCODE_GO_REASONING_EFFORT=max
```

`OPENCODE_GO_REASONING_EFFORT` (default `max`) is sent as `reasoning_effort`
in the OpenAI-compatible envelope, only to the models listed in
`OPENCODE_GO_REASONING_EFFORT_MODELS` (default
`space-bunny-free,deepseek-v4.1-flash-free`). Empty value disables the
parameter.

If the resolved model fails at the LLM layer (after its own retries), the
call is retried once with `OPENCODE_GO_FALLBACK_MODEL` before the error
propagates. The fallback span is traced with the model and error class it
recovers from. An empty `OPENCODE_GO_FALLBACK_MODEL` disables the fallback.

## Chat-only third tier: Groq

The product chat (`create_chat_llm_provider`) can race the OpenCode primary
against a Groq backup (`openai/gpt-oss-120b`) and return the first valid
answer. It is OFF by default and only builds when all of these hold:

- `GROQ_CHAT_FALLBACK_ENABLED=true`
- `GROQ_API_KEY` set
- `GROQ_FREE_PLAN_CONFIRMED=true` and `GROQ_ZDR_CONFIRMED=true` (free plan
  and zero data retention confirmed by the operator)

Optional first backup, tried BEFORE Groq; Groq is used only if Gemini fails or its
output is rejected (sequential, never in parallel): Gemini `gemini-3.5-flash-lite`, then `gemini-3.8-flash` (free tier). OFF by default; needs
`GEMINI_CHAT_FALLBACK_ENABLED=true`, `GEMINI_API_KEY` and
`GEMINI_FREE_PLAN_CONFIRMED=true` (operator confirms the key's project has no
billing, otherwise usage is charged). The same truthfulness guards apply.

Backup output passes through the same truthfulness validators as the primary
(the former lexical educational/no-advice filter was removed in #1127) and never receives
DeepSeek aliases or `effort=max`. This tier exists for chat resilience only;
research workflows do not use it.

## Free cascade (optional provider)

`LLM_PROVIDER=cascade` builds `CascadeProvider`: Gemini AI Studio
(`gemini-3.8-flash`) -> OpenRouter `:free` -> OpenCode, using only members
with a key. Per-member timeouts (~20 s) sit under a 60 s total cap. Privacy:
with cascade, any prompt can reach the Gemini free tier (Google may use it to
improve its products); cost-guarded flows (LLM proposals, bottleneck, news
narrative) reject cascade outright. OpenRouter `:free` does not guarantee
strict `json_schema`.

## Application contract

```text
LLMProvider
- complete
- structured_output
- task model overrides
- provider/model trace metadata
```

The backend uses one OpenAI-compatible adapter with provider name
`opencode-go`, plus the optional `cascade` and the chat-only `groq` backup
described above. There are no OpenAI or Anthropic provider settings in the
application configuration.

## Task routing

All task routes default to `deepseek-v4.1-flash-free`:

- Extraction
- Classification and news materiality
- Company chat
- Thesis updates
- Deep research
- Red-team review
- Document synthesis
- Tool workflows

A model override via `OPENCODE_GO_MODEL` or the task override map is still
sent to OpenCode Go; it never selects another provider.

## Cost and reliability

OpenCode Go applies its own subscription quotas and model limits. GerarAI keeps
request timeout, retry, daily cap, and monthly cap controls in the backend so
expensive workflows remain bounded. Provider failures are surfaced as typed
LLM errors and do not create unsupported financial facts.

The API key is a secret and must live only in local `.env` files or deployment
secret stores. It must never be committed, placed in `config.yaml`, or exposed
in client-side code.

See the official model/endpoint list at:

https://opencode.ai/docs/zen/
