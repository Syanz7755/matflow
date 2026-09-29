# Node Preview Specification

This document defines MatFlow's deterministic progressive-output preview contract. It is normative input for maintainers and for models that propose or scaffold a ToolSpec.

## Safety boundary

A preview summarizes an already produced, schema-validated node output. It must not execute a model, arbitrary HTML, JavaScript, SQL, shell code, notebook cells, or an unreviewed renderer. Preview generation is bounded, deterministic, and safe to repeat. The full output remains the source of truth.

## ToolSpec declaration

`preview_spec.version` is `1.0`. `preview_spec.outputs` maps an output port name to one built-in renderer:

- `text`: bounded plain text; HTML is displayed as text.
- `table_head`: at most 50 rows and 100 columns, with smaller defaults preferred.
- `image`: a validated PNG, JPEG, or WebP artifact reference. Arbitrary remote URLs and SVG are not rendered.
- `json_tree`: a bounded JSON tree with limited depth and collection size.

Each rule may set `max_rows`, `max_columns`, and `max_characters` within the server limits. Unknown renderers or invalid limits reject the ToolSpec. If a port has no rule, MatFlow selects a safe renderer from the output shape and records that a fallback was used.

## Human review

Every node may set `review_policy.after_run`. The executor first completes the node and validates its output, then creates the preview. When review is enabled, the node enters `waiting` and no downstream node runs until the user chooses Continue, Revise node, or Stop run.

## Custom rendering

If the built-in renderers cannot express a scientifically useful preview, a developer may propose a renderer implementation together with tests and a bounded output schema. Generated code remains draft and cannot run until it is reviewed, installed, and activated through the Tool Registry lifecycle.
