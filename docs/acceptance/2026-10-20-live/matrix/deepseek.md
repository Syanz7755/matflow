# Online routing evaluation

Generated 2026-10-20T14:45:32+00:00 - Jev `off` - repeats 1 - registry: shipped reference catalogue (17 agent-selectable tools).
Scope: routing-label coverage only; this does not verify DAG equivalence, execution, numerical accuracy or scientific validity.
Models evaluated: deepseek-official-flash, deepseek-official-v4-pro.

Intervals are Wilson 95% on repeat 0 (n = cases/steps, so they are wide). See `docs/ROUTING_EVALUATION.md` for definitions and limitations.

## Dataset

- 10 labelled cases (teaching_lab: 9, long_prompt: 1); language {'zh': 5, 'en': 5}; expectation {'positive': 6, 'gap': 2, 'human': 2}.
- 0 excluded for missing gold labels; 3 duplicate prompts removed.

## Headline per model (repeat 0)

| model | workflow exact match | exact match excl. transport-failed plans | step top-1 (analysis tools) | correct gap | correct escalation | false-null | needs-human (actions) | Jev->LLM fallback | parse fail | plan latency s (med/p90) |
|---|---|---|---|---|---|---|---|---|---|---|
| deepseek-official-flash | 100% (10/10) [72-100] | 100% (10/10) [72-100] (0% (0/10) [0-28] plans hit a transport error) | 100% (10/10) [72-100] | 100% (2/2) [34-100] | 100% (2/2) [34-100] | 0% (0/10) [0-28] | 12% (4/34) [5-27] | n/a | 0% (0/51) [0-7] | 18.0 / 24.2 |
| deepseek-official-v4-pro | 100% (10/10) [72-100] | 100% (10/10) [72-100] (0% (0/10) [0-28] plans hit a transport error) | 100% (10/10) [72-100] | 100% (2/2) [34-100] | 100% (2/2) [34-100] | 0% (0/10) [0-28] | 9% (3/33) [3-24] | n/a | 0% (0/50) [0-7] | 129.8 / 223.6 |

## By language: workflow exact match / step top-1 (analysis tools)

| model | zh exact | en exact | zh top-1 | en top-1 |
|---|---|---|---|---|
| deepseek-official-flash | 100% (5/5) [57-100] | 100% (5/5) [57-100] | 100% (5/5) [57-100] | 100% (5/5) [57-100] |
| deepseek-official-v4-pro | 100% (5/5) [57-100] | 100% (5/5) [57-100] | 100% (5/5) [57-100] | 100% (5/5) [57-100] |

## Agreement

- Cross-model disagreement (case level, 2 models): 0% (0/10) [0-28]; step level: 0% (0/14) [0-22]; zh 0% (0/5) [0-43], en 0% (0/5) [0-43].
- Self-consistency across repeats (share of cases with identical routing every run): not measured (repeats = 1).

## By domain: workflow exact match

| domain | deepseek-official-flash | deepseek-official-v4-pro |
|---|---|---|
| ambiguous | 100% (1/1) [21-100] | 100% (1/1) [21-100] |
| eis | 100% (2/2) [34-100] | 100% (2/2) [34-100] |
| ftir | 100% (2/2) [34-100] | 100% (2/2) [34-100] |
| safety | 100% (1/1) [21-100] | 100% (1/1) [21-100] |
| tga | 100% (1/1) [21-100] | 100% (1/1) [21-100] |
| uvvis | 100% (1/1) [21-100] | 100% (1/1) [21-100] |
| xrd | 100% (2/2) [34-100] | 100% (2/2) [34-100] |

## Other rates (repeat 0)

| model | null-action rate | plan needs-human | wrong tool on gold step | invalid choice | plan failed | transport error | LLM call latency s (med/p90) |
|---|---|---|---|---|---|---|---|
| deepseek-official-flash | 9% (3/34) [3-23] | 80% (8/10) [49-94] | 0% (0/12) [0-24] | 0% (0/34) [0-10] | 0% (0/10) [0-28] | 0% (0/51) [0-7] | 1.5 / 6.9 |
| deepseek-official-v4-pro | 6% (2/33) [2-20] | 80% (8/10) [49-94] | 0% (0/12) [0-24] | 0% (0/33) [0-10] | 0% (0/10) [0-28] | 0% (0/50) [0-7] | 6.4 / 73.7 |

## Misses (0 of 20 runs)

