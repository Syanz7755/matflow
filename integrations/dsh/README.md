# MatFlow integration for DeepSeek Harness

This local Cordis plugin adds three pieces that the generic DSH MCP bridge does
not provide by itself:

- MatFlow-specific operating instructions in the model system prompt;
- an approval gate for every MatFlow write or execution tool (and fail-safe
  approval for future unclassified MatFlow tools);
- `matflow_import_local_dataset`, a guarded bridge from a DSH workspace or
  attachment path to MatFlow's upload endpoint.

Install and verify the dedicated profile with:

```powershell
uv run matflow configure-dsh --profile matflow
uv run matflow diagnose --dsh
uv run matflow start-dsh
```
