# Routing diagnostic — 2026-10-19

This is a diagnostic of the configured planning path, not an accuracy benchmark or a Jev comparison.

## Recorded evidence

The [raw report](2026-10-19-routing-smoke-off.json) contains nine real plans:
one synthetic Chinese EIS request, three models, three repeats, Jev off. All nine
ended as `planned` and covered the expected routing labels. No plan was executed
by this evaluation. The [rendered report](2026-10-19-routing-smoke-off.md) retains
the per-plan observations and latency statistics. A single unique request cannot
support a general accuracy claim, a model ranking, a language comparison or
scientific validity.

The request timeout was 300 seconds per LLM call; it is not an overall plan
deadline. Total observed plan times ranged from 77.67 to 375.34 seconds. The
models were `qwen`, `deepseek-chat` and `deepseek-reasoner`. `minimax` returned
HTTP 403 during availability probing and was excluded. No credentials or real
research datasets were written into these reports.

Command, from the repository root:

```powershell
uv run python examples/evaluate_routing_online.py --models qwen,deepseek-chat,deepseek-reasoner,minimax --sources known_answer --limit 1 --repeats 3 --jev off --timeout 300 --workers 3 --per-model 1 --checkpoint .tmp/portfolio-routing-off.jsonl --out-json docs/evaluation/2026-10-19-routing-smoke-off.json --out-md docs/evaluation/2026-10-19-routing-smoke-off.md
```

Use a fresh checkpoint after code, dataset or fixture changes. The recorded run
started before the test-suite relocation in this work session; its experiment
fingerprint records that earlier code state. The Markdown and aggregate metrics
were subsequently regenerated from its unchanged observations with the corrected
metric implementation; no additional model calls were made during reanalysis.

## Why the old reasoner score was misleading

The earlier local 18-case report recorded `deepseek-reasoner` as 3/18 passing,
with **13/18 plans failing during decomposition due to `TimeoutError`**. Its 12
returned replies had zero recorded JSON parse failures. The stored evidence
therefore does not support attributing the 17% headline to `<think>` parsing or
semantic incompetence. The new successful request confirms that the model can
complete this planning protocol at least on this one case with a longer timeout;
it does not identify why the earlier requests timed out or validate all cases.

## Jev status and remaining validation

A fresh loopback health probe found the LLM gateway healthy and Jev port 4079
refusing connections. No semantic HTTP 400 was reproduced. Reading the local
gateway source showed it converts model load/scoring `ValueError`, `RuntimeError`
and `OSError` into HTTP 400, so the status alone cannot establish a request-schema
bug. The earlier handoff's Windows error 1455 remains historical information.

Still required before quoting routing quality:

- Restore and diagnose both Jev profiles, capturing a bounded error detail.
- Run the expanded labelled set with on/off modes and three repeats, using separate experiment fingerprints; distinguish genuine Jev decisions from LLM fallback.
- Independently review labels, add multi-step research cases and check graph/parameter correctness and execution separately.
- Retain transport and harness failures, disclose any retry-selected results, and report scenario-level uncertainty instead of treating prompt variants or steps as independent samples.
