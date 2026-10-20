# Live acceptance scripts

These scripts check the running product over its public surfaces; they do not
import backend runtime objects and they read no credential.

| Script | What it checks | Needs |
|---|---|---|
| `check_workflow_api.py` | Upload a dataset, build a four-node typed EIS workflow, run it with a post-run review gate, assert the pause stops downstream work, continue it, assert the real result values, then run the pinned MgO QE replay demo | a running backend (`scripts/start_demo.ps1`) and the EIS fixture in `examples/data/` |

```powershell
# backend from scripts/start_demo.ps1 (default 127.0.0.1:8000)
.\.venv\Scripts\python.exe scripts\live_acceptance\check_workflow_api.py

# another instance
$env:MATFLOW_API = 'http://127.0.0.1:8022/api'
$env:MATFLOW_EVIDENCE = '.tmp/live/api-check'
.\.venv\Scripts\python.exe scripts\live_acceptance\check_workflow_api.py
```

Exit code 0 means every assertion passed; response bodies are archived under the
evidence folder. The manual browser operation is described in
`docs/acceptance/2026-10-20-live/OPERATOR_RUNBOOK.zhcn.md`.
