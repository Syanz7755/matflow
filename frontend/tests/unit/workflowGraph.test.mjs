import test from 'node:test';
import assert from 'node:assert/strict';
import { buildWorkflowGraphModel } from '../../src/workflowGraph.mjs';

const registry = {
  source: { label: 'Source', category: 'Input', version: '1.0.0', inputs: {}, outputs: { raw: 'RawData', metadata: 'Artifact' } },
  transform: { label: 'Transform', category: 'Transform', version: '1.2.0', inputs: { raw: 'RawData', config: 'Artifact' }, outputs: { table: 'TypedTable' } },
};

test('creates one visual handle for every declared input and output port', () => {
  const model = buildWorkflowGraphModel({
    version: 2,
    nodes: [
      { id: 'source-1', type: 'source', position: { x: 10, y: 20 } },
      { id: 'transform-1', type: 'transform', position: { x: 400, y: 20 } },
    ],
    edges: [
      { id: 'raw-edge', source: 'source-1', source_port: 'raw', target: 'transform-1', target_port: 'raw' },
      { id: 'metadata-edge', source: 'source-1', source_port: 'metadata', target: 'transform-1', target_port: 'config' },
    ],
  }, registry);

  assert.deepEqual(model.nodes[0].data.outputs.map((port) => port.id), ['raw', 'metadata']);
  assert.deepEqual(model.nodes[1].data.inputs.map((port) => port.id), ['raw', 'config']);
  assert.deepEqual(model.edges.map((edge) => [edge.sourceHandle, edge.targetHandle]), [['raw', 'raw'], ['metadata', 'config']]);
  assert.deepEqual(model.edges.map((edge) => edge.type), ['default', 'default']);
  assert.deepEqual(model.edges.map((edge) => edge.markerEnd?.type), ['arrowclosed', 'arrowclosed']);
  assert.deepEqual(model.issues, []);
});

test('reports malformed graph input and excludes invalid edges from rendering', () => {
  const model = buildWorkflowGraphModel({
    nodes: [
      { id: 'source-1', type: 'source' },
      { id: 'transform-1', type: 'transform' },
    ],
    edges: [
      { id: 'bad-type', source: 'source-1', source_port: 'metadata', target: 'transform-1', target_port: 'raw' },
      { id: 'bad-port', source: 'source-1', source_port: 'missing', target: 'transform-1', target_port: 'config' },
    ],
  }, registry);

  assert.equal(model.edges.length, 0);
  assert.deepEqual(model.issues.map((item) => item.code), ['type_mismatch', 'unknown_port']);
});

test('detects cycles and multiple edges occupying one input port', () => {
  const loopRegistry = {
    loop: { label: 'Loop', category: 'Test', inputs: { value: 'Artifact' }, outputs: { value: 'Artifact' } },
  };
  const model = buildWorkflowGraphModel({
    nodes: [{ id: 'a', type: 'loop' }, { id: 'b', type: 'loop' }, { id: 'c', type: 'loop' }],
    edges: [
      { id: 'ab', source: 'a', source_port: 'value', target: 'b', target_port: 'value' },
      { id: 'cb', source: 'c', source_port: 'value', target: 'b', target_port: 'value' },
      { id: 'ba', source: 'b', source_port: 'value', target: 'a', target_port: 'value' },
    ],
  }, loopRegistry);

  assert.ok(model.issues.some((item) => item.code === 'occupied_input'));
  assert.ok(model.issues.some((item) => item.code === 'cycle'));
});

test('accepts parent output into child input and resolves abstract cast ports', () => {
  const definitions = {
    Measurement: { name: 'Measurement', parents: [] },
    EISMeasurement: { name: 'EISMeasurement', parents: ['Measurement'] },
    Plot: { name: 'Plot', parents: [] },
  };
  const inheritedRegistry = {
    source: { label: 'Source', outputs: { value: 'Measurement' }, inputs: {} },
    sink: { label: 'Sink', inputs: { value: 'EISMeasurement' }, outputs: { plot: 'Plot' } },
    type_cast: { label: 'Cast', abstract: true, inputs: { value: 'RawData' }, outputs: { value: 'RawData' } },
  };
  const model = buildWorkflowGraphModel({
    nodes: [
      { id: 'source', type: 'source' },
      { id: 'sink', type: 'sink' },
      { id: 'cast', type: 'type_cast', params: { source_type: 'EISMeasurement', target_type: 'Plot' } },
    ],
    edges: [
      { id: 'inherited', source: 'source', source_port: 'value', target: 'sink', target_port: 'value' },
      { id: 'cast-input', source: 'source', source_port: 'value', target: 'cast', target_port: 'value' },
    ],
  }, inheritedRegistry, definitions);

  assert.deepEqual(model.issues, []);
  assert.equal(model.nodes[2].data.inputs[0].dataType, 'EISMeasurement');
  assert.equal(model.nodes[2].data.outputs[0].dataType, 'Plot');
});
