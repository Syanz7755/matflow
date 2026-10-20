# Full impedance-spectrum prompt: backend-only rerun report

> Historical snapshot: this report records the behavior of the workspace as it was on 2026-09-30. A later backend again provided a round-limited `/api/chat`; the original results are kept here as regression evidence and do not represent the interface state on 2026-10-01. Current judgments follow `docs/PROJECT_STATUS.md` and the code tests.

> Scope note: this document is an EBrick Reference Case report, not a Platform Core specification. Multi-branch planning, the Tool lifecycle and generic quality gating are platform concerns; the furnace program, Cp/G conversion, impedance diagnostics and mechanism analysis belong to the EIS Domain Package or to this case.

## Summary

On this run MatFlow formed no plan, generated no domain tool and built no workflow. The final graph stayed at Graph v0 with 0 nodes and 0 edges. The acceptance condition "must be a non-linear DAG" therefore clearly failed; this is not poor topology planning but the current backend never executing a planning stage at all.

In the current architecture the MatFlow core backend is the authority for the workspace, type validation, routing, GraphPatch validation and execution, and it no longer contains an LLM agent. `POST /api/chat` returns "built-in agent is retired" and requires external AI clients to work through the versioned HTTP API or the standalone MCP bridge. The legacy switch was not enabled for this run, because it applies only to migration and does not represent the current product path.

## The expected non-linear structure

A complete task should have a topology with at least these branches, joins and gates:

```text
                            ┌─ furnace-program document parsing ─┐
upload & checks ─┬─ raw scan parsing ┤                                    ├─ time→temperature mapping ─ Cp/G→Z ─ group by temperature
                 └─ metadata/units ──┘                                    │
                                                                          ├─ data integrity / frequency coverage ─┐
                                                                          ├─ KK/Lin-KK physical consistency ──────├─ quality summary ─ quality gate
                                                                          └─ multi-candidate circuit fit compare ─┘                   │
                                                                                                        ┌─ fail: localisation / re-measure advice
                                                                                                        └─ pass ─┬─ DRT / process decomposition
                                                                                                                 ├─ equivalent-circuit contribution shares
                                                                                                                 └─ charts and report summary
```

It needs at least three branch points and two join/gate points, and when quality fails the mechanism-contribution nodes must not be scheduled.

## Actual backend calls and results

1. `POST /api/reset`: isolated the test successfully and produced an empty graph.
2. `POST /api/uploads` of the original `.md` rule document: failed, the backend does not support Markdown.
3. Mirroring the same content as `.txt` and uploading: the upload succeeded, but `GET /api/uploads/{id}` still classified it as `binary`, so the runtime could not see the furnace-program content.
4. `GET /api/uploads/{id}` on the CSV: succeeded, recognising 33027 rows, 11 columns and fields such as time, curve, frequency, `primary` and `secondary`.
5. `POST /api/chat`: rejected by the current backend; the built-in agent is retired.
6. `POST /api/route`: tested separately with the original Chinese text, the normalized version that drifted into English, and the normalized version that kept Chinese.
7. `POST /api/node-library/prompt-build`: tested separately with the three prompts, and it returned only unregistered, non-executable generic node templates.
8. `GET /api/state`: still 0 nodes and 0 edges at the end.

## Routing comparison

| Input version | Candidates | Selection | Result |
|---|---:|---|---|
| original Chinese | 0 | none | human confirmation required |
| first normalization, accidentally translated into English | 6 | `ebrick_case05_import` | Jev disagreed, human confirmation required |
| Chinese normalization with same-language protection added | 0 | none | human confirmation required |

All six candidates for the English version were pushed to 100% by lexical scoring, and no more accurate stage planning was obtained. Laya selected an old AI-revised import node, the semantic model selected the generic import node, and the final routing result selected the EBrick import alias again. That shows the improvement came mainly from the router recognising only English tokens, not from structural normalization helping the system understand a complex task.

In other words: the normalized English text improved recall but not selection quality, and it certainly did not generate a multi-node DAG.

## Tool construction result

`prompt-build` produced the label `1 2 3 4 5 6 NyquistBode` for the original Chinese and `1 ... 2 ... 3 ... 4` for the Chinese normalized version, because the builder strips non-ASCII characters. The English-drift version produced the more readable label `Context The user provides attachments containing`.

But the actual contract of all three templates is identical:

```json
{
  "category": "Derived",
  "inputs": {"input": "TypedTable"},
  "outputs": {"output": "TypedTable"},
  "params": {"method": "default"}
}
```

They contain no furnace-program parsing, no Cp/G-to-impedance conversion, no KK diagnostics, no circuit fitting, no DRT, no quality gating and no numerical implementation, and nothing is registered automatically. They therefore cannot be called "a tool that was written".

## Should every input be normalized unconditionally

Making an LLM normalize the single unavoidable entry point is not recommended. A two-track approach is suggested:

1. The original prompt is always the authoritative record and is never overwritten.
2. The normalization result is a derived planning/retrieval view and goes to the planner alongside the original text.
3. Programmatically check fidelity for file names, paths, numbers, units, negations, conditional statements, quality gates and topology requirements.
4. Fall back to the original text automatically when normalization fails, drifts in language, or loses constraints.
5. If the only goal is to improve English lexical retrieval, generate a separate `retrieval_query_en`; do not translate the whole user request and replace the original with it.
6. Record the model, version, input hash, normalization output and the diff, so the process is auditable.

On this run the first normalization turned Chinese into English, which already proves that a system prompt alone cannot guarantee semantic fidelity. The script subsequently added a hard same-language check, covered by five unit tests.

## The most critical product gaps today

1. The current product path lacks a real external AI planning client or a connected MCP agent, so a complete prompt cannot enter the "read attachments → research the method → generate a tool → produce a GraphPatch → validate → execute" loop.
2. The upload/inspection layer cannot read Markdown or ordinary rule text, so furnace-program data cannot enter the planning context.
3. Chinese recall in the router is zero, while English recall is polluted by stop words and a large number of 100% ties.
4. The tool manager's search/adapt/build switches are all off, and the EIS domain tool recipe is outside the existing declarative XRD/FTIR recipe capability.
5. Platform Core does not yet provide generic multi-Artifact join, quality gating and conditional execution semantics; the types and decision rules of the diagnostic Artifacts themselves should be defined by the EIS Domain Package.

The next step is therefore not to keep tuning this one prompt, but to fill in the external planning agent, readable document types, multilingual retrieval, the domain tool lifecycle and DAG gating semantics first.
