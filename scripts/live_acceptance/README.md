# Live acceptance scripts

These scripts check the running product over its public surfaces; they do not
import backend runtime objects and they read no credential.

| Script | What it checks | Needs |
|---|---|---|
| `check_workflow_api.py` | Upload a dataset, build a four-node typed EIS workflow, run it with a post-run review gate, assert the pause stops downstream work, continue it, assert the real result values, then run the pinned MgO QE replay demo | a running backend (`scripts/start_demo.ps1`) and the EIS fixture in `examples/data/` |
| `check_demo_ui.mjs` | Walk the WebUI in the demo recording order (S0–S10) and assert every screen plus the server state: import, typed graph, review gate, stop-run, export/import, QE replay, Chinese routing, narrow viewport. Reports PASS / FAIL / KNOWN; exit 0 means no FAIL | a running backend + WebUI with an **empty** workspace, Node.js, and `playwright` in the sibling `matflow-frontend` checkout |
| `capture_demo_frames.mjs` | Drive the real WebUI through the demo storyboard (import → typed graph → review gate → continue → clear → QE replay → Chinese routing), write one 1920×1080 PNG per scene plus a JSON evidence file with the values the narration quotes. Read-only with respect to the repository; it does write to the workspace it is pointed at | a running backend + WebUI with an **empty** workspace, Node.js, and `playwright` installed in the sibling `matflow-frontend` checkout |

```powershell
# backend from scripts/start_demo.ps1 (default 127.0.0.1:8000)
.\.venv\Scripts\python.exe scripts\live_acceptance\check_workflow_api.py

# another instance
$env:MATFLOW_API = 'http://127.0.0.1:8022/api'
$env:MATFLOW_EVIDENCE = '.tmp/live/api-check'
.\.venv\Scripts\python.exe scripts\live_acceptance\check_workflow_api.py
```

```powershell
# demo-order health check (fresh-save stack; mutates the workspace it points at)
$env:MATFLOW_SAVE = 'demo-health'
$env:MATFLOW_LLM_CONFIG = 'config\llm-deepseek.json'
pwsh -File scripts\start_demo.ps1          # in one terminal
node scripts\live_acceptance\check_demo_ui.mjs
# expected: summary: {"PASS":57,"KNOWN":2} and exit code 0
```

```powershell
# demo frames: start a fresh-save stack first (see the demo tutorial), then
$env:MATFLOW_SAVE = 'demo-video'
$env:MATFLOW_LLM_CONFIG = 'config\llm-deepseek.json'
pwsh -File scripts\start_demo.ps1          # in one terminal
node scripts\live_acceptance\capture_demo_frames.mjs
# overrides: MATFLOW_WEB_URL, MATFLOW_API, MATFLOW_FRONTEND_REPO,
#            MATFLOW_FRAME_OUT, MATFLOW_FRAME_EVIDENCE, MATFLOW_VIEWPORT
```

Exit code 0 means every assertion passed; response bodies are archived under the
evidence folder. The manual browser operation is described in
`docs/acceptance/2026-10-20-live/OPERATOR_RUNBOOK.zhcn.md`; the video-recording
walkthrough (storyboard, feature list, narration, OBS settings) is
`docs/acceptance/2026-10-20-live/demo-tutorial/DEMO_TUTORIAL.zhcn.md`.
