# MatFlow MCP Runtime Policy

Use MatFlow as the authoritative workspace for materials workflow state.

- Inspect workspace state and datasets before making claims about them.
- Use only registered tool and data-type identifiers returned by MatFlow.
- Validate every graph patch before proposing that it be applied.
- Ask the user for confirmation immediately before importing data, applying a patch, executing a workflow, or submitting a human decision.
- Treat version conflicts and validation failures as evidence that the workspace changed; reread state instead of retrying blindly.
- Never invent observations, outputs, file contents, or successful execution.
- Stop at a waiting human-decision node and present its prompt and allowed options.
