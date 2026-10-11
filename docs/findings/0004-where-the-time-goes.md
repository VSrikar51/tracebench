# 0004. Where the time goes in one agent run

- **Date:** 2026-10-11
- **Model:** `qwen3.5:4b` via Ollama, thinking off, temperature 0, context 8192
- **Hardware:** MacBook Air M2, 8GB
- **Trace:** `a31281ba16ef816db23f6aa8727694bc`
- **Task:** damaged cat litter on order 1001 (same as finding 0003)

## Trace

| Span | ms | Tokens in | Tokens out |
|---|---|---|---|
| invoke_agent support_agent | 30,191 | | |
| chat qwen3.5:4b | 11,997 | 1,386 | 31 |
| execute_tool get_customer | 73 | | |
| chat qwen3.5:4b | 2,865 | 1,511 | 49 |
| execute_tool get_order | 21 | | |
| chat qwen3.5:4b | 2,862 | 1,856 | 28 |
| execute_tool search_policies | 20 | | |
| chat qwen3.5:4b | 6,248 | 2,366 | 88 |
| execute_tool issue_refund | 12 | | |
| chat qwen3.5:4b | 6,084 | 2,537 | 112 |

## Observations

1. **Model calls are 99.6% of the run time** (29,995 ms); the four tools take
   126 ms in total. Speeding up the agent means fewer or faster model calls,
   not faster tools.
2. **The first call is a cold start** (12.0 s): the model was reloaded after
   being idle. Later calls with more input tokens took about 2.9 s, because
   Ollama reuses its processing of the shared prompt prefix (system prompt
   and tool definitions).
3. **Output tokens drive per-call latency** once warm: calls writing 88–112
   tokens took about 6 s; calls writing about 30 took about 3 s.
4. **Input tokens are 97% of all tokens** (9,656 in vs. 308 out), because
   every call re-sends the whole conversation. Input will dominate the cost
   on paid models; prompt caching is the main lever.
5. **The same wrong refund was issued** ($37.98), with slightly different
   wording and token counts from finding 0003. Temperature 0 is nearly, not
   perfectly, repeatable; evals should judge outcomes, not exact wording.

## What this motivates

- **Warm up the model** before timed eval runs, so cold starts don't skew
  latency results.
- Track **steps per task** as an efficiency metric.
- Record **cached input tokens** separately when paid providers are added.