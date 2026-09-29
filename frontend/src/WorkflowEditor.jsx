import { useEffect, useMemo, useRef, useState } from 'react';
import WorkflowGraph from './WorkflowGraph.jsx';
import { buildWorkflowGraphModel } from './workflowGraph.mjs';
import {
  buildPatchOperations,
  createNodeFromTool,
  exportWorkflowDocument,
  normalizeImportedGraph,
} from './workflowDraft.mjs';

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function JsonParamField({ name, value, onChange }) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [error, setError] = useState('');

  useEffect(() => { setText(JSON.stringify(value, null, 2)); setError(''); }, [value]);

  function commit() {
    try {
      onChange(JSON.parse(text));
      setError('');
    } catch (parseError) {
      setError(`Invalid JSON: ${parseError.message}`);
    }
  }

  return (
    <label className="inspector-field">
      <span>{name.replaceAll('_', ' ')}</span>
      <textarea value={text} onChange={(event) => setText(event.target.value)} onBlur={commit} rows="5" aria-invalid={Boolean(error)} />
      {error && <small className="field-error">{error}</small>}
    </label>
  );
}

function ParameterField({ name, value, datasets, dataTypes = [], onChange }) {
  if (name === 'upload_id') {
    return (
      <label className="inspector-field">
        <span>Dataset</span>
        <select value={String(value ?? '')} onChange={(event) => onChange(event.target.value)}>
          <option value="">Choose an imported dataset</option>
          {datasets.map((dataset) => <option value={dataset.id} key={dataset.id}>{dataset.name}</option>)}
        </select>
      </label>
    );
  }
  if (name === 'source_type' || name === 'target_type') {
    return (
      <label className="inspector-field">
        <span>{name.replaceAll('_', ' ')}</span>
        <select value={String(value ?? '')} onChange={(event) => onChange(event.target.value)}>
          {dataTypes.map((type) => <option value={type} key={type}>{type}</option>)}
        </select>
      </label>
    );
  }
  if (typeof value === 'object' && value !== null) {
    return <JsonParamField name={name} value={value} onChange={onChange} />;
  }
  if (typeof value === 'number') {
    return (
      <label className="inspector-field">
        <span>{name.replaceAll('_', ' ')}</span>
        <input type="number" value={value} onChange={(event) => onChange(Number(event.target.value))} />
      </label>
    );
  }
  const longText = name === 'instructions' || String(value ?? '').length > 80;
  return (
    <label className="inspector-field">
      <span>{name === 'instructions' ? 'Script / instructions' : name.replaceAll('_', ' ')}</span>
      {longText
        ? <textarea value={String(value ?? '')} onChange={(event) => onChange(event.target.value)} rows="7" />
        : <input value={String(value ?? '')} onChange={(event) => onChange(event.target.value)} />}
    </label>
  );
}

function downloadWorkflow(graph) {
  const blob = new Blob([JSON.stringify(exportWorkflowDocument(graph), null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${graph.graph_id || 'matflow-workflow'}.matflow.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function PreviewPanel({ preview }) {
  if (!preview) return <p className="muted">Run this node to create a bounded preview.</p>;
  if (preview.kind === 'table') {
    const columns = [...new Set((preview.rows ?? []).flatMap((row) => Object.keys(row ?? {})))];
    return <div className="preview-table-wrap"><table className="preview-table"><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{preview.rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{String(row?.[column] ?? '')}</td>)}</tr>)}</tbody></table></div>;
  }
  if (preview.kind === 'text') return <pre className="preview-text">{preview.text}</pre>;
  if (preview.kind === 'image') return <img className="preview-image" src={preview.url} alt="Node output preview" />;
  return <pre className="preview-json">{JSON.stringify(preview.data ?? preview, null, 2)}</pre>;
}

function CanvasIcon({ name }) {
  const paths = {
    import: <><path d="M12 3v11" /><path d="m8 7 4-4 4 4" /><path d="M5 13v6h14v-6" /></>,
    export: <><path d="M12 14V3" /><path d="m8 7 4-4 4 4" /><path d="M5 13v6h14v-6" /></>,
    discard: <><path d="M5 5h14" /><path d="M9 5V3h6v2" /><path d="m8 9 8 8" /><path d="m16 9-8 8" /></>,
    save: <><path d="M5 3h12l2 2v14H5z" /><path d="M8 3v6h8V3" /><path d="M8 19v-6h8v6" /></>,
    run: <path d="m8 5 10 7-10 7z" />,
    panels: <><path d="M4 5h16v14H4z" /><path d="M10 5v14" /></>,
    inspector: <><path d="M4 5h16v14H4z" /><path d="M14 5v14" /></>,
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">{paths[name]}</svg>;
}

function RenameNodeDialog({ node, onClose, onRename }) {
  const [label, setLabel] = useState(node.label ?? '');
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  function submit(event) {
    event.preventDefault();
    const nextLabel = label.trim();
    if (!nextLabel) return;
    onRename(nextLabel);
    onClose();
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="rename-dialog" role="dialog" aria-modal="true" aria-labelledby="rename-node-title">
        <header><div><span>Workflow node</span><h2 id="rename-node-title">Rename node</h2></div><button type="button" aria-label="Close rename node dialog" onClick={onClose}>×</button></header>
        <form onSubmit={submit}>
          <label htmlFor="node-label">Node name<input ref={inputRef} id="node-label" value={label} onChange={(event) => setLabel(event.target.value)} maxLength="120" required /></label>
          <footer><button type="button" className="quiet-button" onClick={onClose}>Cancel</button><button type="submit" className="save-button" disabled={!label.trim()}>Rename node</button></footer>
        </form>
      </section>
    </div>
  );
}

function RevisionDialog({ node, providers, busy, onClose, onPropose, onApply, onAddProvider }) {
  const [prompt, setPrompt] = useState('');
  const [providerId, setProviderId] = useState(providers[0]?.id ?? 'local_litellm');
  const provider = providers.find((item) => item.id === providerId) ?? providers[0];
  const [model, setModel] = useState(provider?.models?.[0] ?? 'qwen');
  const [proposal, setProposal] = useState(null);
  const [decisions, setDecisions] = useState({});
  const [error, setError] = useState('');
  const [showProviderForm, setShowProviderForm] = useState(false);
  const [providerDraft, setProviderDraft] = useState({ provider_id: '', label: '', base_url: '', api_key_env: '', models: '' });

  useEffect(() => { setModel(provider?.models?.[0] ?? 'qwen'); }, [providerId]);

  async function propose(event) {
    event.preventDefault();
    setError('');
    try {
      const next = await onPropose({ node_id: node.id, prompt, provider_id: providerId, model });
      setProposal(next);
      setDecisions(Object.fromEntries(next.edge_plan.filter((edge) => edge.status === 'suggested').map((edge) => [edge.edge_id, edge.suggested_port])));
    } catch (requestError) { setError(requestError.message); }
  }

  async function apply() {
    setError('');
    try { await onApply(proposal.proposal_id, decisions); onClose(); }
    catch (requestError) { setError(requestError.message); }
  }

  async function addProvider(event) {
    event.preventDefault(); setError('');
    try {
      const created = await onAddProvider({ ...providerDraft, models: providerDraft.models.split(',').map((item) => item.trim()).filter(Boolean) });
      setProviderId(created.id); setShowProviderForm(false);
    } catch (requestError) { setError(requestError.message); }
  }

  const unresolved = proposal?.edge_plan.filter((edge) => edge.status !== 'exact' && !(edge.edge_id in decisions)).length ?? 0;
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="revision-dialog" role="dialog" aria-modal="true" aria-labelledby="revision-title">
        <header><div><span>Isolated proposal</span><h2 id="revision-title">Modify {node.label ?? node.type}</h2></div><button type="button" aria-label="Close revision dialog" onClick={onClose}>×</button></header>
        {!proposal ? <form onSubmit={propose} className="revision-prompt-form">
          <label>What should change?<textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows="7" placeholder="Describe the behavior, parameters, ports, and preview you need." required /></label>
          <div className="revision-model-grid"><label>Provider<select value={providerId} onChange={(event) => setProviderId(event.target.value)}>{providers.map((item) => <option key={item.id} value={item.id}>{item.label}{item.key_configured ? '' : ' · key missing'}</option>)}</select></label><label>Model<select value={model} onChange={(event) => setModel(event.target.value)}>{(provider?.models ?? []).map((item) => <option key={item}>{item}</option>)}</select></label></div>
          <button type="button" className="provider-toggle" onClick={() => setShowProviderForm((current) => !current)}>{showProviderForm ? 'Hide API setup' : 'Add OpenAI-compatible API'}</button>
          {showProviderForm && <div className="provider-form" onKeyDown={(event) => { if (event.key === 'Enter') event.preventDefault(); }}><label>ID<input value={providerDraft.provider_id} onChange={(event) => setProviderDraft((current) => ({ ...current, provider_id: event.target.value }))} /></label><label>Label<input value={providerDraft.label} onChange={(event) => setProviderDraft((current) => ({ ...current, label: event.target.value }))} /></label><label>Base URL<input value={providerDraft.base_url} onChange={(event) => setProviderDraft((current) => ({ ...current, base_url: event.target.value }))} placeholder="https://provider.example/v1" /></label><label>Key environment variable<input value={providerDraft.api_key_env} onChange={(event) => setProviderDraft((current) => ({ ...current, api_key_env: event.target.value }))} placeholder="PROVIDER_API_KEY" /></label><label>Models, comma separated<input value={providerDraft.models} onChange={(event) => setProviderDraft((current) => ({ ...current, models: event.target.value }))} /></label><button type="button" className="quiet-button" onClick={addProvider}>Save API configuration</button><small>Put the matching secret in the local .env file. MatFlow never sends it to the browser.</small></div>}
          {error && <p className="modal-error" role="alert">{error}</p>}
          <footer><button type="button" className="quiet-button" onClick={onClose}>Cancel</button><button type="submit" className="save-button" disabled={busy || !prompt.trim()}>{busy ? 'Generating…' : 'Generate proposal'}</button></footer>
        </form> : <div className="revision-review">
          <div className="revision-summary"><div><span>Current</span><strong>{proposal.original_tool.label}</strong><code>{proposal.original_tool.tool_id}</code></div><div><span>Proposed</span><strong>{proposal.proposed_tool.label}</strong><code>{proposal.proposed_tool.tool_id}</code></div></div>
          <section><h3>Definition changes</h3><p>{proposal.proposed_tool.description}</p><pre>{JSON.stringify({ inputs: proposal.proposed_tool.inputs, outputs: proposal.proposed_tool.outputs, params: proposal.proposed_tool.params, preview_spec: proposal.proposed_tool.preview_spec }, null, 2)}</pre></section>
          <section><h3>Connection migration</h3>{proposal.edge_plan.length ? <div className="edge-plan">{proposal.edge_plan.map((edge) => <label key={edge.edge_id} className={`edge-plan-row edge-${edge.status}`}><span><strong>{edge.edge_id}</strong><small>{edge.direction} · {edge.data_type} · {edge.status}</small></span>{edge.status === 'exact' ? <code>{edge.old_port}</code> : <select value={edge.edge_id in decisions ? (decisions[edge.edge_id] ?? '__drop__') : ''} onChange={(event) => setDecisions((current) => ({ ...current, [edge.edge_id]: event.target.value === '__drop__' ? null : event.target.value }))}><option value="">Choose mapping</option>{edge.candidates.map((port) => <option key={port} value={port}>{port}</option>)}<option value="__drop__">Drop connection</option></select>}</label>)}</div> : <p className="muted">This node has no incident connections.</p>}</section>
          {proposal.risk_findings.length > 0 && <div className="revision-risk"><strong>Review required</strong>{proposal.risk_findings.map((finding) => <p key={finding}>{finding}</p>)}</div>}
          {error && <p className="modal-error" role="alert">{error}</p>}
          <footer><button type="button" className="quiet-button" onClick={() => setProposal(null)}>Back</button><button type="button" className="save-button" onClick={apply} disabled={busy || unresolved > 0 || proposal.requires_code_review}>{proposal.requires_code_review ? 'Executor review required' : unresolved ? `Resolve ${unresolved} connection${unresolved === 1 ? '' : 's'}` : 'Apply revision'}</button></footer>
        </div>}
      </section>
    </div>
  );
}

export default function WorkflowEditor({
  graph,
  registry,
  dataTypes = [],
  dataTypeDefinitions = {},
  datasets,
  busy,
  onSave,
  onRun,
  onDecision,
  providers = [],
  onProposeRevision,
  onApplyRevision,
  onAddProvider,
  onStatus,
  workspacePanel,
}) {
  const [draft, setDraft] = useState(() => clone(graph ?? { version: 0, nodes: [], edges: [] }));
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [search, setSearch] = useState('');
  const [notice, setNotice] = useState('Choose a tool to add the first node.');
  const [runResults, setRunResults] = useState([]);
  const [connectMode, setConnectMode] = useState(null);
  const [contextMenu, setContextMenu] = useState(null);
  const [revisionNodeId, setRevisionNodeId] = useState(null);
  const [renameNodeId, setRenameNodeId] = useState(null);
  const [activeSidebarTab, setActiveSidebarTab] = useState('workspace');
  const [drawer, setDrawer] = useState(null);
  const importInput = useRef(null);

  useEffect(() => {
    if (!graph) return;
    setDraft(clone(graph));
    setDirty(false);
    setSelectedNodeId((current) => graph.nodes.some((node) => node.id === current) ? current : null);
  }, [graph]);

  useEffect(() => {
    function cancelConnection(event) { if (event.key === 'Escape') { setConnectMode(null); setContextMenu(null); setDrawer(null); setRenameNodeId(null); } }
    window.addEventListener('keydown', cancelConnection);
    return () => window.removeEventListener('keydown', cancelConnection);
  }, []);

  const selectedNode = draft.nodes.find((node) => node.id === selectedNodeId) ?? null;
  const selectedTool = selectedNode ? registry[selectedNode.type] : null;
  const operations = useMemo(() => buildPatchOperations(graph ?? {}, draft), [graph, draft]);
  const graphModel = useMemo(() => buildWorkflowGraphModel(draft, registry, dataTypeDefinitions), [draft, registry, dataTypeDefinitions]);
  const tools = Object.entries(registry).filter(([toolId, tool]) => {
    const query = search.trim().toLowerCase();
    return !query || `${toolId} ${tool.label} ${tool.category} ${tool.description ?? ''}`.toLowerCase().includes(query);
  });

  function updateDraft(updater, message) {
    setDraft((current) => updater(clone(current)));
    setDirty(true);
    if (message) setNotice(message);
  }

  function addNode(toolId) {
    const tool = registry[toolId];
    updateDraft((current) => {
      const node = createNodeFromTool(toolId, tool, current);
      current.nodes.push(node);
      setSelectedNodeId(node.id);
      return current;
    }, `${tool.label} added to the draft.`);
  }

  function removeNodes(nodeIds) {
    const removing = new Set(nodeIds);
    updateDraft((current) => ({
      ...current,
      nodes: current.nodes.filter((node) => !removing.has(node.id)),
      edges: current.edges.filter((edge) => !removing.has(edge.source) && !removing.has(edge.target)),
    }), `${nodeIds.length} node${nodeIds.length === 1 ? '' : 's'} removed from the draft.`);
    if (removing.has(selectedNodeId)) setSelectedNodeId(null);
  }

  function connect(connection) {
    if (!connection.source || !connection.target || !connection.sourceHandle || !connection.targetHandle) return;
    const base = `${connection.source}-${connection.sourceHandle}--${connection.target}-${connection.targetHandle}`;
    let edgeId = base;
    let index = 2;
    while (draft.edges.some((edge) => edge.id === edgeId)) edgeId = `${base}-${index++}`;
    const edge = {
      id: edgeId,
      source: connection.source,
      source_port: connection.sourceHandle,
      target: connection.target,
      target_port: connection.targetHandle,
    };
    const candidate = { ...draft, edges: [...draft.edges, edge] };
    const model = buildWorkflowGraphModel(candidate, registry, dataTypeDefinitions);
    if (model.issues.length) {
      setNotice(model.issues.at(-1).message);
      onStatus({ kind: 'error', message: model.issues.at(-1).message });
      return;
    }
    updateDraft(() => candidate, `Connected ${edge.source_port} to ${edge.target_port}.`);
  }

  function updateSelectedNode(key, value) {
    updateDraft((current) => {
      const node = current.nodes.find((item) => item.id === selectedNodeId);
      if (node) node[key] = value;
      return current;
    });
  }

  function updateParameter(name, value) {
    updateDraft((current) => {
      const node = current.nodes.find((item) => item.id === selectedNodeId);
      if (node) node.params = { ...node.params, [name]: value };
      return current;
    });
  }

  function toggleReview(nodeId, checked) {
    updateDraft((current) => {
      const node = current.nodes.find((item) => item.id === nodeId);
      if (node) node.review_policy = { ...(node.review_policy ?? {}), after_run: checked, prompt: node.review_policy?.prompt ?? 'Review this result before continuing.' };
      return current;
    }, checked ? 'Review will pause downstream execution after this node.' : 'Review pause disabled for this node.');
  }

  function clickPort(port) {
    if (port.direction === 'output') {
      setConnectMode({ nodeId: port.nodeId, portId: port.portId, dataType: port.dataType });
      setNotice(`Connecting ${port.dataType}. Choose a highlighted input port or press Esc.`);
      return;
    }
    if (!connectMode) { setNotice('Start from an output port, then choose an input port.'); return; }
    connect({ source: connectMode.nodeId, sourceHandle: connectMode.portId, target: port.nodeId, targetHandle: port.portId });
    setConnectMode(null);
  }

  function openNodeMenu(nodeId, point) {
    setSelectedNodeId(nodeId);
    setContextMenu({ nodeId, x: point.x ?? point.left, y: point.y ?? point.bottom });
  }

  async function applyRevision(proposalId, edgeDecisions) {
    const next = await onApplyRevision(proposalId, edgeDecisions);
    setDraft(clone(next));
    setDirty(false);
    setNotice(`Node revision applied atomically as Graph v${next.version}.`);
  }

  async function saveDraft() {
    if (graphModel.issues.length) throw new Error(graphModel.issues[0].message);
    if (!operations.length) {
      setNotice('The workflow is already saved.');
      return graph;
    }
    const saved = await onSave({
      base_version: graph.version,
      rationale: 'Saved from the MatFlow workflow editor',
      operations,
    });
    setDraft(clone(saved));
    setDirty(false);
    setNotice(`Saved as graph v${saved.version}.`);
    return saved;
  }

  async function runWorkflow() {
    try {
      if (!draft.nodes.length) throw new Error('Add at least one node before running the workflow.');
      if (dirty) await saveDraft();
      const outcome = await onRun({ restart: true });
      setRunResults(outcome.results ?? []);
      setNotice(outcome.results?.some((item) => item.error) ? 'The run stopped at an error. Select the node to inspect it.' : 'Workflow run finished.');
    } catch (error) {
      setNotice(error.message);
      onStatus({ kind: 'error', message: error.message });
    }
  }

  async function importWorkflow(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const imported = normalizeImportedGraph(JSON.parse(await file.text()), registry, graph.version);
      const model = buildWorkflowGraphModel(imported, registry, dataTypeDefinitions);
      if (model.issues.length) throw new Error(model.issues.map((item) => item.message).join(' '));
      setDraft(imported);
      setSelectedNodeId(imported.nodes[0]?.id ?? null);
      setDirty(true);
      setNotice(`Imported ${file.name}. Review and save to apply it.`);
    } catch (error) {
      setNotice(error.message);
      onStatus({ kind: 'error', message: error.message });
    } finally {
      event.target.value = '';
    }
  }

  async function submitDecision(option) {
    try {
      const result = await onDecision(selectedNode.id, option);
      setDraft(clone(result.state));
      setNotice(`Decision “${option}” submitted.`);
    } catch (error) {
      setNotice(error.message);
      onStatus({ kind: 'error', message: error.message });
    }
  }

  const revisionNode = draft.nodes.find((node) => node.id === revisionNodeId);
  const renameNode = draft.nodes.find((node) => node.id === renameNodeId);

  const inspector = (
    <>
      <div className="panel-title"><strong>Inspector</strong>{selectedNode && <code>{selectedNode.id}</code>}</div>
      {selectedNode ? (
        <div className="inspector-content">
          <label className="inspector-field"><span>Node label</span><input value={selectedNode.label ?? ''} onChange={(event) => updateSelectedNode('label', event.target.value)} /></label>
          <div className="inspector-identity"><span>{selectedTool?.category}</span><strong>{selectedTool?.label}</strong><code>{selectedNode.type} · v{selectedNode.tool_version}</code></div>
          <div className="inspector-params"><h3>Parameters</h3>{Object.entries(selectedNode.params ?? {}).map(([name, value]) => <ParameterField key={name} name={name} value={value} datasets={datasets} dataTypes={dataTypes} onChange={(next) => updateParameter(name, next)} />)}</div>
          <section className="preview-panel"><h3>Progressive preview</h3><PreviewPanel preview={selectedNode.preview} /></section>
          {selectedNode.status === 'waiting' && selectedNode.review_state?.status === 'pending' && <div className="decision-actions"><h3>{selectedNode.review_policy?.prompt ?? 'Review this result before continuing.'}</h3><button type="button" onClick={() => submitDecision('continue')} disabled={busy}>Continue</button><button type="button" onClick={() => setRevisionNodeId(selectedNode.id)} disabled={busy}>Revise node</button><button type="button" onClick={() => submitDecision('stop')} disabled={busy}>Stop run</button></div>}
          {selectedNode.output && <details className="node-output"><summary>Latest output</summary><pre>{JSON.stringify(selectedNode.output, null, 2)}</pre></details>}
          <button type="button" className="danger-button" onClick={() => removeNodes([selectedNode.id])}>Delete node</button>
        </div>
      ) : (
        <div className="inspector-empty"><strong>Select a node</strong><p>Edit its label, parameters, dataset, or Skill Node instructions here.</p><button type="button" onClick={() => updateDraft((current) => ({ ...current, nodes: [], edges: [] }), 'Workflow cleared in the draft.')} disabled={!draft.nodes.length}>Clear workflow</button></div>
      )}
    </>
  );

  return (
    <section className="workflow-editor" aria-label="Workflow editor">
      {drawer && <button type="button" className="drawer-backdrop" aria-label="Close sidebar" onClick={() => setDrawer(null)} />}
      <div className="editor-grid">
        <aside className={`workbench-sidebar workbench-left ${drawer === 'left' ? 'drawer-open' : ''}`} aria-label="Workflow workspace">
          <div className="sidebar-tab-row">
            <div className="sidebar-tabs" role="tablist" aria-label="Left sidebar">
              <button type="button" role="tab" id="workspace-tab" aria-selected={activeSidebarTab === 'workspace'} aria-controls="workspace-panel" onClick={() => setActiveSidebarTab('workspace')}>Workspace</button>
              <button type="button" role="tab" id="library-tab" aria-selected={activeSidebarTab === 'library'} aria-controls="library-panel" onClick={() => setActiveSidebarTab('library')}>Tool library</button>
            </div>
            <button type="button" className="drawer-close" aria-label="Close workspace sidebar" onClick={() => setDrawer(null)}>×</button>
          </div>
          <div id="workspace-panel" role="tabpanel" aria-labelledby="workspace-tab" hidden={activeSidebarTab !== 'workspace'} className="workspace-panel">{workspacePanel}</div>
          <div id="library-panel" role="tabpanel" aria-labelledby="library-tab" hidden={activeSidebarTab !== 'library'} className="tool-palette">
            <div className="panel-title"><strong>Tool library</strong><span aria-live="polite">{tools.length}</span></div>
            <label className="tool-search"><span className="visually-hidden">Search tools</span><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search tools" /></label>
            <div className="tool-catalog">
              {tools.map(([toolId, tool]) => (
                <button type="button" className="tool-card" key={toolId} onClick={() => addNode(toolId)} disabled={busy}>
                  <span>{tool.category}</span><strong>{tool.label}</strong><small>{tool.description}</small><code>{Object.keys(tool.inputs ?? {}).length} in · {Object.keys(tool.outputs ?? {}).length} out</code>
                </button>
              ))}
            </div>
          </div>
        </aside>

        <div className="editor-stage">
          <div className="canvas-action-group" aria-label="Workflow file and run actions">
            <button type="button" className="canvas-action" aria-label="Import workflow JSON" title="Import JSON" onClick={() => importInput.current?.click()} disabled={busy}><CanvasIcon name="import" /></button>
            <input ref={importInput} className="visually-hidden" type="file" aria-label="Import workflow JSON file" accept=".json,.matflow.json,application/json" onChange={importWorkflow} />
            <button type="button" className="canvas-action" aria-label="Export workflow JSON" title="Export JSON" onClick={() => downloadWorkflow(draft)} disabled={!draft.nodes.length}><CanvasIcon name="export" /></button>
            <button type="button" className="canvas-action" aria-label="Discard draft changes" title="Discard changes" onClick={() => { setDraft(clone(graph)); setDirty(false); setNotice('Draft changes discarded.'); }} disabled={!dirty || busy}><CanvasIcon name="discard" /></button>
            <button type="button" className="canvas-action canvas-action-save" aria-label="Save workflow" title="Save workflow" onClick={() => saveDraft().catch((error) => { setNotice(error.message); onStatus({ kind: 'error', message: error.message }); })} disabled={!dirty || busy || graphModel.issues.length > 0}><CanvasIcon name="save" /></button>
            <button type="button" className="canvas-action canvas-action-run" aria-label="Run workflow from start" title="Run from start" onClick={runWorkflow} disabled={busy || !draft.nodes.length}><CanvasIcon name="run" /></button>
          </div>
          <div className="canvas-drawer-controls">
            <button type="button" className="canvas-action" aria-label="Open workspace sidebar" title="Open workspace" onClick={() => setDrawer('left')}><CanvasIcon name="panels" /></button>
            <button type="button" className="canvas-action" aria-label="Open inspector" title="Open inspector" onClick={() => setDrawer('right')}><CanvasIcon name="inspector" /></button>
          </div>
          <div className="graph-state-chip" aria-live="polite"><span className={dirty ? 'draft-dot' : 'saved-dot'} aria-hidden="true" />{dirty ? `${operations.length} unsaved change${operations.length === 1 ? '' : 's'}` : `Saved · Graph v${graph?.version ?? 0}`}</div>
          <WorkflowGraph
            graph={draft}
            registry={registry}
            dataTypeDefinitions={dataTypeDefinitions}
            editable
            showHeading={false}
            selectedNodeId={selectedNodeId}
            onConnect={connect}
            onNodeClick={(_event, node) => setSelectedNodeId(node.id)}
            onPaneClick={() => setSelectedNodeId(null)}
            onNodesDelete={(nodes) => removeNodes(nodes.map((node) => node.id))}
            onEdgesDelete={(edges) => updateDraft((current) => ({ ...current, edges: current.edges.filter((edge) => !edges.some((removed) => removed.id === edge.id)) }), 'Connection removed from the draft.')}
            onNodeDragStop={(_event, node) => updateDraft((current) => { const target = current.nodes.find((item) => item.id === node.id); if (target) target.position = node.position; return current; })}
            onNodeContextMenu={(event, node) => { event.preventDefault(); openNodeMenu(node.id, { x: event.clientX, y: event.clientY }); }}
            onNodeMenu={(nodeId, rect) => openNodeMenu(nodeId, { x: rect.right, y: rect.bottom })}
            onReviewToggle={toggleReview}
            connectMode={connectMode}
            onPortClick={clickPort}
          />
          {connectMode && <div className="connect-helper" role="status">Select a compatible {connectMode.dataType} input <button type="button" onClick={() => setConnectMode(null)}>Cancel</button></div>}
          <div className="editor-notice" role="status" aria-live="polite"><span className={dirty ? 'draft-dot' : 'saved-dot'} aria-hidden="true" />{notice}</div>
          {runResults.length > 0 && <details className="run-results"><summary>Latest workflow run</summary><ol aria-label="Latest workflow run">{runResults.map((item, index) => <li className={item.error ? 'run-error' : ''} key={`${item.node_id ?? 'run'}-${index}`}><strong>{item.node_id ?? 'Workflow'}</strong><span>{item.error ?? item.result?.kind ?? 'Completed'}</span></li>)}</ol></details>}
        </div>

        <aside className={`workbench-sidebar node-inspector ${drawer === 'right' ? 'drawer-open' : ''}`} aria-label="Node inspector">
          <button type="button" className="drawer-close inspector-close" aria-label="Close inspector" onClick={() => setDrawer(null)}>×</button>
          {inspector}
        </aside>
      </div>
      {contextMenu && <div className="node-context-menu" role="menu" style={{ left: Math.min(contextMenu.x, window.innerWidth - 230), top: Math.min(contextMenu.y, window.innerHeight - 230) }}>
        <button type="button" role="menuitem" onClick={() => { setRenameNodeId(contextMenu.nodeId); setContextMenu(null); }}>Rename node</button>
        <button type="button" role="menuitem" onClick={() => { setRevisionNodeId(contextMenu.nodeId); setContextMenu(null); }}>Modify with AI</button>
        <label><input type="checkbox" checked={Boolean(draft.nodes.find((node) => node.id === contextMenu.nodeId)?.review_policy?.after_run)} onChange={(event) => toggleReview(contextMenu.nodeId, event.target.checked)} /> Review after run</label>
        <button type="button" role="menuitem" onClick={() => { setSelectedNodeId(contextMenu.nodeId); setContextMenu(null); }}>Preview latest output</button>
        <button type="button" role="menuitem" className="menu-danger" onClick={() => { removeNodes([contextMenu.nodeId]); setContextMenu(null); }}>Delete node</button>
      </div>}
      {renameNode && <RenameNodeDialog node={renameNode} onClose={() => setRenameNodeId(null)} onRename={(label) => updateDraft((current) => { const node = current.nodes.find((item) => item.id === renameNode.id); if (node) node.label = label; return current; }, `Renamed node to ${label}.`)} />}
      {revisionNode && <RevisionDialog node={revisionNode} providers={providers} busy={busy} onClose={() => setRevisionNodeId(null)} onPropose={onProposeRevision} onApply={applyRevision} onAddProvider={onAddProvider} />}
    </section>
  );
}
