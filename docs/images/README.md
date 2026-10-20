# Screenshots to capture

The root [README](../../README.md) links to the images below. They do not exist yet; the workbench lives in the separate `matflow-frontend` repository, so capture them from a running backend + WebUI (`uv run matflow start --ui webui`). Save PNGs (about 1600 px wide, light theme, no personal data or API keys visible) with exactly these names.

| File | Screen | State to capture |
|---|---|---|
| `workbench-overview.png` | Full workbench window | Empty or freshly reset workspace right after the QE replay demo has finished: prompt/chat area, workflow graph and result area all visible in one frame. |
| `workflow-graph.png` | Workflow graph view | The four-node QE replay workflow (MgO structure -> `pw.x` input generation -> archived QE output replay -> result parsing) with node states and parameters visible. |
| `task-result.png` | Result of the finished task | Parsed total energy, Fermi energy and convergence evidence shown, with the "historical replay" label visible. |

Optional recording: `qe-replay-demo.gif` or `.mp4` (20-40 s, under 10 MB). Start from an empty workspace, click **Run MgO QE replay demo**, show the graph filling in node by node, then the parsed result. Link it from the README only if you capture it.

Suggested demo prompt (the pinned request the demo uses): `For pristine MgO SCF, generate a QE input and report energy and convergence.`

Notes: the demo requires an empty workspace (use a fresh save, e.g. `uv run matflow start --save screenshots`). It is a local historical replay and does not run `pw.x`; keep any caption honest about that.
