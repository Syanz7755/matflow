# Online routing evaluation

Generated 2026-10-20T15:00:28+00:00 - Jev `off` - repeats 1 - registry: shipped reference catalogue (17 agent-selectable tools).
Scope: routing-label coverage only; this does not verify DAG equivalence, execution, numerical accuracy or scientific validity.
Models evaluated: deepseek-chat.

Intervals are Wilson 95% on repeat 0 (n = cases/steps, so they are wide). See `docs/ROUTING_EVALUATION.md` for definitions and limitations.

## Dataset

- 10 labelled cases (teaching_lab: 9, long_prompt: 1); language {'zh': 5, 'en': 5}; expectation {'positive': 6, 'gap': 2, 'human': 2}.
- 0 excluded for missing gold labels; 3 duplicate prompts removed.

## Headline per model (repeat 0)

| model | workflow exact match | exact match excl. transport-failed plans | step top-1 (analysis tools) | correct gap | correct escalation | false-null | needs-human (actions) | Jev->LLM fallback | parse fail | plan latency s (med/p90) |
|---|---|---|---|---|---|---|---|---|---|---|
| deepseek-chat | 100% (10/10) [72-100] | 100% (10/10) [72-100] (0% (0/10) [0-28] plans hit a transport error) | 100% (10/10) [72-100] | 100% (2/2) [34-100] | 100% (2/2) [34-100] | 0% (0/10) [0-28] | 9% (3/33) [3-24] | n/a | 0% (0/57) [0-6] | 74.6 / 110.0 |

## By language: workflow exact match / step top-1 (analysis tools)

| model | zh exact | en exact | zh top-1 | en top-1 |
|---|---|---|---|---|
| deepseek-chat | 100% (5/5) [57-100] | 100% (5/5) [57-100] | 100% (5/5) [57-100] | 100% (5/5) [57-100] |

## Agreement

- Cross-model disagreement (case level, 1 models): n/a; step level: n/a; zh n/a, en n/a.
- Self-consistency across repeats (share of cases with identical routing every run): not measured (repeats = 1).

## By domain: workflow exact match

| domain | deepseek-chat |
|---|---|
| ambiguous | 100% (1/1) [21-100] |
| eis | 100% (2/2) [34-100] |
| ftir | 100% (2/2) [34-100] |
| safety | 100% (1/1) [21-100] |
| tga | 100% (1/1) [21-100] |
| uvvis | 100% (1/1) [21-100] |
| xrd | 100% (2/2) [34-100] |

## Other rates (repeat 0)

| model | null-action rate | plan needs-human | wrong tool on gold step | invalid choice | plan failed | transport error | LLM call latency s (med/p90) |
|---|---|---|---|---|---|---|---|
| deepseek-chat | 9% (3/33) [3-24] | 80% (8/10) [49-94] | 0% (0/12) [0-24] | 0% (0/33) [0-10] | 0% (0/10) [0-28] | 0% (0/57) [0-6] | 4.5 / 26.8 |

## Misses (0 of 10 runs)

