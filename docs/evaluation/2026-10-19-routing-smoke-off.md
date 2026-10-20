# Online routing evaluation

Generated 2026-10-19T08:50:41+00:00 - Jev `off` - repeats 3 - registry: shipped reference catalogue (17 agent-selectable tools).
Scope: routing-label coverage only; this does not verify DAG equivalence, execution, numerical accuracy or scientific validity.
Models evaluated: deepseek-chat, deepseek-reasoner, qwen. Unavailable (skipped): minimax (HTTP 403).

Intervals are Wilson 95% on repeat 0 (n = cases/steps, so they are wide). See `docs/ROUTING_EVALUATION.md` for definitions and limitations.

## Dataset

- 1 labelled cases (known_answer: 1); language {'zh': 1}; expectation {'positive': 1}.
- 0 excluded for missing gold labels; 3 duplicate prompts removed.

## Headline per model (repeat 0)

| model | workflow exact match | exact match excl. transport-failed plans | step top-1 (analysis tools) | correct gap | correct escalation | false-null | needs-human (actions) | Jev->LLM fallback | parse fail | plan latency s (med/p90) |
|---|---|---|---|---|---|---|---|---|---|---|
| deepseek-chat | 100% (1/1) [21-100] | 100% (1/1) [21-100] (0% (0/1) [0-79] plans hit a transport error) | 100% (1/1) [21-100] | n/a | n/a | 0% (0/1) [0-79] | 0% (0/4) [0-49] | n/a | 0% (0/6) [0-39] | 171.2 / 171.2 |
| deepseek-reasoner | 100% (1/1) [21-100] | 100% (1/1) [21-100] (0% (0/1) [0-79] plans hit a transport error) | 100% (1/1) [21-100] | n/a | n/a | 0% (0/1) [0-79] | 0% (0/4) [0-49] | n/a | 0% (0/7) [0-35] | 262.7 / 262.7 |
| qwen | 100% (1/1) [21-100] | 100% (1/1) [21-100] (0% (0/1) [0-79] plans hit a transport error) | 100% (1/1) [21-100] | n/a | n/a | 0% (0/1) [0-79] | 0% (0/4) [0-49] | n/a | 0% (0/6) [0-39] | 80.1 / 80.1 |

## By language: workflow exact match / step top-1 (analysis tools)

| model | zh exact | en exact | zh top-1 | en top-1 |
|---|---|---|---|---|
| deepseek-chat | 100% (1/1) [21-100] | n/a | 100% (1/1) [21-100] | n/a |
| deepseek-reasoner | 100% (1/1) [21-100] | n/a | 100% (1/1) [21-100] | n/a |
| qwen | 100% (1/1) [21-100] | n/a | 100% (1/1) [21-100] | n/a |

## Agreement

- Cross-model disagreement (case level, 3 models): 0% (0/1) [0-79]; step level: 0% (0/1) [0-79]; zh 0% (0/1) [0-79], en n/a.
- Self-consistency across repeats (share of cases with identical routing every run): deepseek-chat 100% (1/1) [21-100], deepseek-reasoner 100% (1/1) [21-100], qwen 100% (1/1) [21-100].

## By domain: workflow exact match

| domain | deepseek-chat | deepseek-reasoner | qwen |
|---|---|---|---|
| eis | 100% (1/1) [21-100] | 100% (1/1) [21-100] | 100% (1/1) [21-100] |

## Other rates (repeat 0)

| model | null-action rate | plan needs-human | wrong tool on gold step | invalid choice | plan failed | transport error | LLM call latency s (med/p90) |
|---|---|---|---|---|---|---|---|
| deepseek-chat | 0% (0/4) [0-49] | 0% (0/1) [0-79] | 0% (0/1) [0-79] | 0% (0/4) [0-49] | 0% (0/1) [0-79] | 0% (0/6) [0-39] | 18.1 / 63.4 |
| deepseek-reasoner | 0% (0/4) [0-49] | 0% (0/1) [0-79] | 0% (0/1) [0-79] | 0% (0/4) [0-49] | 0% (0/1) [0-79] | 0% (0/7) [0-35] | 19.6 / 83.0 |
| qwen | 0% (0/4) [0-49] | 0% (0/1) [0-79] | 0% (0/1) [0-79] | 0% (0/4) [0-49] | 0% (0/1) [0-79] | 0% (0/6) [0-39] | 2.8 / 36.0 |

## Misses (0 of 9 runs)

