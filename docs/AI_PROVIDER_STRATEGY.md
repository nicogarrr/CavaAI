# AI Provider Strategy

Date: 2026-08-16

## Decision

CavaAI uses **OpenCode Go as its only LLM provider**. All backend research
workflows and frontend Inngest jobs use the same OpenAI-compatible API:

```text
https://opencode.ai/zen/go/v1/chat/completions
```

The default model is `deepseek-v4-flash`, which is listed by the official
OpenCode Go documentation as a chat-completions model. The model can be
changed through `OPENCODE_GO_MODEL` without adding another provider.

## Configuration

```env
OPENCODE_GO_API_KEY=replace_with_an_opencode_go_key
OPENCODE_GO_BASE_URL=https://opencode.ai/zen/go/v1
OPENCODE_GO_MODEL=deepseek-v4-flash
```

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

All task routes default to `deepseek-v4-flash`:

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

https://opencode.ai/docs/es/go/
