import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildPatchOperations,
  createNodeFromTool,
  exportWorkflowDocument,
  normalizeImportedGraph,
} from '../../src/workflowDraft.mjs';

const registry = {
  source: { label: 'Source', version: '1.0.0', params: { path: '' }, inputs: {}, outputs: { raw: 'RawData' } },
  sink: { label: 'Sink', version: '1.0.0', params: { title: 'Result' }, inputs: { raw: 'RawData' }, outputs: { artifact: 'Artifact' } },
};

test('creates unique nodes with independent default parameter objects', () => {
  const graph = { nodes: [], edges: [] };
  const first = createNodeFromTool('source', registry.source, graph);
  graph.nodes.push(first);
  const second = createNodeFromTool('source', registry.source, graph);
  first.params.path = 'changed.csv';

  assert.equal(first.id, 'source-1');
  assert.equal(second.id, 'source-2');
  assert.equal(second.params.path, '');
});

test('builds a deterministic patch for metadata, node, and edge edits', () => {
  const saved = {
    nodes: [{ id: 'a', type: 'source', label: 'Source', params: { path: '' }, position: { x: 0, y: 0 } }],
    edges: [],
  };
  const draft = {
    nodes: [
      { ...saved.nodes[0], label: 'Input', position: { x: 12, y: 34 } },
      { id: 'b', type: 'sink', label: 'Sink', params: { title: 'Result' }, position: { x: 300, y: 0 } },
    ],
    edges: [{ id: 'a-b', source: 'a', source_port: 'raw', target: 'b', target_port: 'raw' }],
  };

  const operations = buildPatchOperations(saved, draft);
  assert.deepEqual(operations.map((item) => item.op), ['update_node', 'add_node', 'connect']);
  assert.deepEqual(operations[0].changes, { label: 'Input', position: { x: 12, y: 34 } });
});

test('normalizes an exported workflow for safe re-import and resets runtime output', () => {
  const document = exportWorkflowDocument({
    graph_id: 'demo',
    nodes: [{ id: 'a', type: 'source', params: { path: 'file.csv' }, position: { x: 1, y: 2 }, status: 'completed', output: { kind: 'RawData' } }],
    edges: [],
  });
  const imported = normalizeImportedGraph(document, registry, 7);

  assert.equal(imported.version, 7);
  assert.equal(imported.nodes[0].status, 'ready');
  assert.equal(imported.nodes[0].output, null);
  assert.equal(document.graph.nodes[0].output, undefined);
});

test('rejects imports that reference tools outside the active registry', () => {
  assert.throws(
    () => normalizeImportedGraph({ nodes: [{ id: 'x', type: 'missing' }], edges: [] }, registry, 0),
    /Unknown tool/,
  );
});

test('persists per-node review policy as a safe metadata change', () => {
  const saved = { nodes: [{ id: 'a', type: 'source', params: { path: '' }, position: { x: 0, y: 0 }, review_policy: { after_run: false, prompt: 'Review.' } }], edges: [] };
  const draft = structuredClone(saved);
  draft.nodes[0].review_policy.after_run = true;
  const operations = buildPatchOperations(saved, draft);
  assert.deepEqual(operations, [{ op: 'update_node', node_id: 'a', changes: { review_policy: { after_run: true, prompt: 'Review.' } } }]);
});
