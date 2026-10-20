# Screenshots

Captured on **2026-10-20** from a running backend + WebUI (`matflow-backend` + public
`matflow-frontend`), in a fresh save with an empty workspace. PNGs are 1600 px wide, light theme,
contain no personal data or API keys. They show the **offline historical QE replay demo**, not LLM
planning and not a new `pw.x` or Slurm run.

| File | Screen | What the frame shows |
|---|---|---|
| `workbench-overview.png` | Full workbench window | Empty workspace just after connecting: prompt/task entries, tool registry, empty graph and inspector in one frame. |
| `workflow-graph.png` | Workflow graph view | The four-node QE replay workflow (MgO structure → `pw.x` input generation → archived QE output replay → result parsing), node states badged, `Historical output replay · Slurm not submitted` label and parsed values in the inspector. |
| `task-result.png` | Result of the finished task | Progressive preview with `Convergence: converged`, `Total energy: -2417.17683284 Ry`, `Fermi energy`, `SCF iterations: 14` and the source path, under the historical-replay label. |
| `node-review-gate.png` | Post-run review gate | `Parse QE result` node in `Waiting` with **Review** enabled, the result preview still shown, and the review panel offering **Continue / Revise node / Stop run** — the human-confirmation branch. |

Provenance and the full acceptance evidence (commands, expected values, hash checks) are in
[docs/acceptance/2026-10-20/](../acceptance/2026-10-20/REPORT.zhcn.md).

Missing (planned, not captured): a recording (`qe-replay-demo.gif`/`.mp4`) and a screenshot of the
live model-decision / rule-check view, because the 2026-10-20 window did not include online routing.

The suggested demo prompt (the pinned request the demo uses): `For pristine MgO SCF, generate a QE
input and report energy and convergence.` The demo requires an empty workspace
(`uv run matflow start --save screenshots`).
