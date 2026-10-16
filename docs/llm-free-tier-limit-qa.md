# Explicit free-tier limit: isolated evidence and offline replay

## Observed state

On 2026-10-16 at 12:54 CEST, one generic PER canary against GLM 5.3 Flash Free ran in its own bridge and OpenCode 1.19.1 serve, not the production stack and without Nico's account, sessions or portfolio data. The serve logged an upstream rate-limit error about 0.6 seconds after model dispatch. `/session/status` then returned `type=retry`, `action.reason=free_tier_limit`, message `Free usage exceeded, subscribe to Go`, and `next=1792195200239` milliseconds. The next timestamp calculates to 2026-10-17 02:00 CEST. This is the SDK's next attempt, NOT proof of a quota reset, scope, or guaranteed recovery. The canary was aborted and its session deleted as soon as this state was read. No further model calls followed.

Earlier canaries had rate-limit logs without this explicit status. Generic rate-limit messages, HTTP 429 alone and transient retries therefore do not trigger this new branch. This is not a general rate-limit detector.

Official privacy documentation: https://opencode.ai/docs/zen/ . DeepSeek and GLM free are listed as zero-retention/no training. MiMo may use inputs for improvement; Nemotron trials exclude personal/confidential inputs. None has been shown to be a reliable replacement in this incident. No new account or paid tier was created.

## Change

Based on the narrow async/title transport change in #1089, inspect session status in a separate daemon thread, with a 2-second request timeout and a stop event. The response path reads messages first and never waits for that thread. Completion takes priority over a simultaneous quota status. Cleanup sets the stop event without joining an in-flight status read. If the explicit free-tier action is present, raise a fixed Spanish error and return HTTP 429, abort and delete the session. Do not forward the provider's subscription link or message. A valid future `next` timestamp within seven days pauses only this model in this bridge process until that time. Missing, malformed, expired or farther timestamps are not cached. Other models are not paused by inference. Restart loses this cache. Concurrent calls already in progress may still reach the provider.

An unavailable or malformed status endpoint does not discard the primary response. Regular retries continue normally. The original 150-second loop and 60-second ordinary request timeout remain. This is NOT an absolute deadline: ordinary requests, polling and cleanup add time; status inspection is off the response path. No automatic paid alternative and no fabricated model response.

## Verification

22 offline tests, including actual loopback HTTP replay with no upstream credentials/model calls: two bridge requests return 429 in under two seconds each, but only the first creates a session and dispatches a prompt; abort/delete verified. This loopback replay has immediate local responses, not a production latency guarantee. A separate async backend-deadline canary spends a virtual 43 seconds in prompt, then lets the primary finish after one real second while status is blocked for up to two seconds: the valid result arrives before the remaining two seconds of the backend budget expire. Other tests cover 44-second valid primary, transient retry, invalid status shape, status timeout, invalid timestamps, cache expiry and model isolation. Directed Ruff passes with the repository's configuration.

This only reduces waiting and repeated calls after an explicitly reported free-tier limit. It does not restore quota, prevent all concurrent calls, or remove backend retries/hedges. No production deployment or successful production chat is claimed.
