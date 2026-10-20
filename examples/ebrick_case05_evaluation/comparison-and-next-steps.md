# EBrick case 05: expectations, actual run and next steps

> Scope note: this document is a historical evaluation of the EBrick Reference Case. Graph planning, review and state aggregation are Platform Core concerns; Cp/G conversion, complex-impedance types, thresholds and scientific acceptance belong to the EIS Domain Package or to this case and must not become default platform capability.

## Conclusion

This test succeeded at the "orchestration structure" level and failed at the "scientific computation" level, as expected. The ten-node, nine-edge workflow could be imported, executed, paused at human review on the final node, and then completed fully once continue was chosen; but the current so-called Nyquist preview treats `primary=Cp` and `secondary=G` directly as the real and imaginary parts of impedance, which makes it unusable for physical interpretation.

The tool nodes were generated in a local file first, and neither the tool ids, their definitions nor the expected results were placed into the routing prompt. Only after the expectations were frozen were the four reviewed aliases published to the local node registry, because a runtime cannot call nodes its executor cannot see at all. The "invisible" boundary here is therefore: the design process, node definitions and answers are not leaked before routing; at runtime the system is allowed to see only the published node contracts.

## Expected versus actual

| Check | Frozen expectation | Actual result | Verdict |
|---|---|---|---|
| Router's first-choice tool | `ebrick_cp_g_normalize` | `ebrick_case05_import` | Does not match |
| Does routing generate the whole workflow | No; the current router only selects a single tool | No | Matches the capability assessment |
| Routing confidence | Jev may disagree and require confirmation | All five candidates at 100%, Jev disagreed, human confirmation required | Risk materialised |
| Workflow size | 10 nodes, 9 edges | 10 nodes, 9 edges | Matches |
| Final state after first run | the final node waits for human review | `preview-100khz` awaits review | Matches |
| Final state after review | all complete | 10/10 nodes complete | Matches |
| 20 Hz QC | 33027/33027 | 33027/33027 | Matches |
| 1 kHz QC | 33027/22563 | 33027/22563 | Matches |
| 100 kHz QC | 33027/10464 | 33027/10464 | Matches |
| Points per preview | 500 | 500 | Matches the implementation's intent |
| Scientific validity | fail | fail | Negative control materialised |
| First-point coordinates | current implementation about `(-1.00071e-10, -3.68831e-08)`; correct impedance about `(2.428915e7, -8.281386e6)` | exactly consistent with the current broken implementation | Confirms the semantic defect |

The routing error is not random noise but a retrieval and ranking problem: import, normalization and the generic node all scored 100% at once, single-tool routing lacks the stage constraint "the current input is already RawData, so the next step should be column mapping", and the import node was selected in the end. Routing also failed to compose the ordering and three-branch requirements of the prompt into a graph.

Although the three plotting branches hang off QC nodes with different thresholds, all of them plot the same first 500 rows. That shows the current plotting node does not consume the upstream QC mask or the filtered data; it re-reads the original uploaded data. Correct QC numbers do not mean the plot used the QC result.

Another interface problem: while the final node was still Waiting, the header already showed "Workflow run complete". That conflates "the engine stopped executing" with "the business process completed".

## Improvement priorities

### P0: fix the scientific data contract first

1. Add a `cp_g_to_impedance` Tool to the EIS Domain Package that takes frequency `f`, parallel capacitance `Cp` and conductance `G` explicitly and computes `Y = G + j·2πf·Cp`, `Z = 1/Y`; it must also record units, the imaginary-part sign convention, a finite-value check and a physical-quadrant check.
2. Define a `ComplexImpedanceSweep` type in the EIS Domain Package and forbid `plot_nyquist` from accepting an ordinary table that only carries Cp/G semantics.
3. Have QC output the filtered data or a transferable row mask; the plot must consume that output and must not fall back to the uploaded file. Keep 327 sweeps by `curve_index` instead of slicing the first 500 rows.

### P1: upgrade routing into stage-aware graph planning

1. When a prompt contains several actions, return an ordered or branching `GraphPatch` instead of selecting only one tool.
2. Rank using the current input type, node input/output types, completed stages and the target stage together; when RawData already exists, normalization should outrank importing again.
3. Never break a tie at 100% by registry order; on a Jev disagreement, present the candidate differences or explicitly ask the user to choose.
4. Add Chinese and mixed Chinese–English tokenization so Chinese task words do not vanish from lexical fallback. *(Superseded: lexical fallback was removed; routing is a type filter plus a model decision, so Chinese prompts reach the model verbatim.)*

### P1: fix review and state reporting

1. Aggregate the top-level status from node statuses: when any node is Waiting, show "awaiting human review" and never "complete".
2. Show "structural validation" and "scientific validation" separately in the review panel; this run may accept only the former.
3. Add the generic draft Tool → offline evaluation → review → publication lifecycle to Platform Core so hidden test Tools need not be mixed into the production registry in advance.

### P2: establish the EBrick regression baseline

1. Freeze this case's 33027 rows, 327 curves, the three QC counts and the first-point impedance values.
2. Property-test the frequency thresholds: as the threshold rises the number of retained rows must be non-increasing, and a different threshold must change the plotting input.
3. Keep the existing analysis report's 257 successful fits and 70 incomplete or failed fits as an independent reference so the workflow cannot claim an equivalent-circuit fit out of thin air.
4. Parse the furnace program, diameter and thickness from the description file and carry them as traceable metadata through conversion, plotting and fitting.

## Suggested acceptance gate for the next round

The next round must not merely require "all 10 nodes green". It must satisfy at least: the first-point impedance agrees with the analytical calculation; the 20 Hz, 1 kHz and 100 kHz branches take 33027, 22563 and 10464 input rows respectively; the graph is grouped by sweep; the interface stays Waiting before the final review; and routing can generate or suggest a complete multi-stage graph from the same prompt.
