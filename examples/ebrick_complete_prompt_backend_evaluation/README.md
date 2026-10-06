# EBrick complete-prompt backend evaluation

This evaluation submits a realistic Chinese user request to MatFlow's `/api/chat` agent endpoint using the case 05 raw CSV and its furnace-program Markdown document as attachments.

Scope: this directory is a historical EBrick Reference Case, not a Platform Core specification. Branched-DAG planning, Tool lifecycle, and quality-gate behavior are platform concerns; furnace mapping, Cp/G conversion, impedance diagnostics, and scientific outputs belong to an EIS Domain Package or this case.

The expectation is frozen before submission. The test requires a branched DAG with joins and a quality gate; a single linear chain is a failure. All observations, graph mutations, tool proposals and execution attempts are captured from backend responses only. The frontend is not used.

Artifacts:

- `prompt.txt`: original Chinese evaluation prompt.
- `normalized-prompt.txt`: first normalization, retained as evidence of unintended English language drift.
- `normalized-prompt-zh.txt`: guarded same-language normalization.
- `normalization.json` and `normalization-zh.json`: normalization metadata.
- `expected.json`: acceptance criteria frozen before agent submission.
- `actual.json`: compact backend observations.
- `report.md`: comparison, topology assessment, and product recommendations.
