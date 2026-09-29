import { memo, useMemo } from 'react';
import {
  Background,
  BackgroundVariant,
  ConnectionLineType,
  Controls,
  Handle,
  Position,
  ReactFlow,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { buildWorkflowGraphModel, canDataTypeFlow } from './workflowGraph.mjs';

const STATUS_LABELS = {
  ready: 'Ready',
  running: 'Running',
  completed: 'Completed',
  waiting: 'Waiting',
  error: 'Error',
  cancelled: 'Stopped',
};

function Port({ port, direction, nodeId, connectMode, onPortClick, dataTypeDefinitions }) {
  const isInput = direction === 'input';
  const active = connectMode?.nodeId === nodeId && connectMode?.portId === port.id;
  const compatible = isInput && connectMode && canDataTypeFlow(connectMode.dataType, port.dataType, dataTypeDefinitions) && connectMode.nodeId !== nodeId;
  const incompatible = isInput && connectMode && !compatible;
  return (
    <div className={`workflow-port workflow-port-${direction}${active ? ' port-active' : ''}${compatible ? ' port-compatible' : ''}${incompatible ? ' port-incompatible' : ''}`} data-port-id={port.id} title={`${port.id} · ${port.dataType}`}>
      <Handle
        id={port.id}
        type={isInput ? 'target' : 'source'}
        position={isInput ? Position.Left : Position.Right}
        aria-label={`${direction} ${port.id}, ${port.dataType}`}
        isConnectable={port.connectable}
        onClick={(event) => { event.stopPropagation(); onPortClick?.({ nodeId, portId: port.id, dataType: port.dataType, direction }); }}
      />
      <span className="port-name">{port.id}</span>
      <span className="port-type">{port.dataType}</span>
    </div>
  );
}

const WorkflowNode = memo(function WorkflowNode({ data }) {
  return (
    <article className={`workflow-node workflow-node-${data.status}`} aria-label={`${data.label} workflow node`}>
      <header>
        <div>
          <strong>{data.label}</strong>
          <code>{data.toolId} · v{data.toolVersion}</code>
        </div>
        <div className="node-header-actions">
          <label className="node-review-toggle nodrag nopan" title="Pause after this node produces a preview"><input type="checkbox" checked={Boolean(data.reviewPolicy?.after_run)} onChange={(event) => data.onReviewToggle?.(data.nodeId, event.target.checked)} /><span>Review</span></label>
          <button type="button" className="node-menu-button nodrag nopan" aria-label={`Open actions for ${data.label}`} onClick={(event) => { event.stopPropagation(); data.onMenu?.(data.nodeId, event.currentTarget.getBoundingClientRect()); }}>•••</button>
          <span className="node-status"><i aria-hidden="true" />{STATUS_LABELS[data.status] ?? data.status}</span>
        </div>
      </header>
      <div className="node-category">{data.category}</div>
      <div className="port-columns">
        <section aria-label="Input ports">
          <h4>Inputs</h4>
          {data.inputs.length ? data.inputs.map((port) => <Port key={port.id} port={port} direction="input" nodeId={data.nodeId} connectMode={data.connectMode} onPortClick={data.onPortClick} dataTypeDefinitions={data.dataTypeDefinitions} />) : <p className="no-ports">No inputs</p>}
        </section>
        <section aria-label="Output ports">
          <h4>Outputs</h4>
          {data.outputs.length ? data.outputs.map((port) => <Port key={port.id} port={port} direction="output" nodeId={data.nodeId} connectMode={data.connectMode} onPortClick={data.onPortClick} dataTypeDefinitions={data.dataTypeDefinitions} />) : <p className="no-ports">No outputs</p>}
        </section>
      </div>
    </article>
  );
});

const nodeTypes = { workflowNode: WorkflowNode };

export default function WorkflowGraph({
  graph,
  registry,
  dataTypeDefinitions = {},
  className = '',
  editable = false,
  selectedNodeId = null,
  onConnect,
  onNodeClick,
  onPaneClick,
  onNodesDelete,
  onEdgesDelete,
  onNodeDragStop,
  onNodeContextMenu,
  onReviewToggle,
  onNodeMenu,
  connectMode,
  onPortClick,
  showHeading = true,
}) {
  const model = useMemo(() => buildWorkflowGraphModel(graph, registry, dataTypeDefinitions), [graph, registry, dataTypeDefinitions]);
  const hasNodes = model.nodes.length > 0;
  const nodes = model.nodes.map((node) => ({
    ...node,
    selected: node.id === selectedNodeId,
    data: {
      ...node.data,
      nodeId: node.id,
      reviewPolicy: graph.nodes.find((item) => item.id === node.id)?.review_policy,
      connectMode,
      dataTypeDefinitions,
      onPortClick,
      onReviewToggle,
      onMenu: onNodeMenu,
      inputs: node.data.inputs.map((port) => ({ ...port, connectable: editable })),
      outputs: node.data.outputs.map((port) => ({ ...port, connectable: editable })),
    },
  }));

  return (
    <section className={`workflow-graph ${showHeading ? '' : 'workflow-graph-canvas-only'} ${className}`.trim()} aria-labelledby={showHeading ? 'workflow-graph-heading' : undefined}>
      {showHeading && <div className="workflow-graph-heading">
        <div>
          <h2 id="workflow-graph-heading">Workflow graph</h2>
          <p>{editable ? 'Drag nodes, connect matching ports, then save the draft.' : 'Each parameter has its own typed connection point. Drag the canvas to follow the workflow.'}</p>
        </div>
        <span>v{graph?.version ?? 0} · {model.nodes.length} nodes · {model.edges.length} edges</span>
      </div>}

      <div className="workflow-canvas" data-testid="workflow-canvas" role="region" aria-label="Directed workflow graph">
        <ReactFlow
            nodes={nodes}
            edges={model.edges}
            nodeTypes={nodeTypes}
            nodesDraggable={editable}
            nodesConnectable={editable}
            nodesFocusable
            edgesFocusable
            connectionLineType={ConnectionLineType.Bezier}
            connectionLineStyle={{ stroke: '#55738d', strokeWidth: 2.25 }}
            defaultEdgeOptions={{ type: 'default', markerEnd: { type: 'arrowclosed', width: 18, height: 18, color: '#55738d' } }}
            elementsSelectable
            deleteKeyCode={editable ? ['Backspace', 'Delete'] : null}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            onNodesDelete={onNodesDelete}
            onEdgesDelete={onEdgesDelete}
            onNodeDragStop={onNodeDragStop}
            onNodeContextMenu={onNodeContextMenu}
            defaultViewport={{ x: 16, y: 48, zoom: 0.78 }}
            minZoom={0.35}
            maxZoom={1.6}
            aria-label="Directed workflow graph"
          >
            <Background variant={BackgroundVariant.Dots} gap={18} size={1.2} color="#bdc9c4" />
            <Controls showInteractive={false} position="bottom-right" />
          </ReactFlow>
        {!hasNodes && (
          <div className="workflow-empty">
            <svg viewBox="0 0 180 72" aria-hidden="true">
              <path d="M42 36h92" />
              <circle cx="30" cy="36" r="12" />
              <circle cx="146" cy="36" r="12" />
              <path d="m126 28 10 8-10 8" />
            </svg>
            <strong>No workflow nodes yet</strong>
            <p>{editable ? 'Choose a tool from the library to start a workflow.' : 'Apply a validated graph patch to make the server-owned workflow visible here.'}</p>
          </div>
        )}
      </div>

      {model.issues.length > 0 && (
        <div className="graph-issues" role="alert">
          <strong>Graph integrity issue{model.issues.length === 1 ? '' : 's'}</strong>
          <ul>{model.issues.map((item, index) => <li key={`${item.code}-${index}`}>{item.message}</li>)}</ul>
        </div>
      )}
    </section>
  );
}
