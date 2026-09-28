import { useEffect, useId, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const API = (import.meta.env.VITE_MATFLOW_API_URL ?? 'http://127.0.0.1:8000/api').replace(/\/$/, '');

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail ?? 'The MatFlow service could not complete this request.');
  return payload;
}

function uniqueTaskId() {
  return globalThis.crypto?.randomUUID?.() ?? `task-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function RegistryItem({ toolId, tool }) {
  return (
    <li className="registry-item">
      <div>
        <strong>{tool.label}</strong>
        <span className="registered-id">{toolId}</span>
      </div>
      <span className="tool-version">v{tool.version}</span>
    </li>
  );
}

function DecisionRecord({ summary }) {
  if (!summary) {
    return (
      <section className="decision-panel empty-panel" aria-labelledby="decision-heading">
        <div className="section-heading"><span className="section-index">02</span><h2 id="decision-heading">Decision record</h2></div>
        <p>提交研究任务后，这里会保留服务端的候选工具、注册 ID、路由理由与安全处理建议。</p>
      </section>
    );
  }

  const selected = summary.decision?.selected_tools ?? [];
  const candidates = summary.decision?.candidate_tools ?? [];
  const waiting = summary.status === 'waiting_for_confirmation';
  return (
    <section className="decision-panel" aria-labelledby="decision-heading">
      <div className="section-heading">
        <span className="section-index">02</span>
        <div><h2 id="decision-heading">Decision record</h2><p>服务端已记录此任务的可审计路由结果。</p></div>
        <span className={`state-badge ${waiting ? 'state-attention' : 'state-ready'}`}>{waiting ? '需要确认' : '已路由'}</span>
      </div>

      <dl className="audit-facts">
        <div><dt>Task ID</dt><dd>{summary.task_id}</dd></div>
        <div><dt>Trace ID</dt><dd>{summary.trace_id}</dd></div>
        <div><dt>Graph version</dt><dd>v{summary.input_context?.graph_version ?? '—'}</dd></div>
      </dl>

      <div className="prompt-evidence"><span>User prompt</span><p>{summary.user_prompt}</p></div>

      <div className="decision-columns">
        <div>
          <h3>Selected registered tool</h3>
          {selected.length ? <ul className="tool-list">{selected.map((tool) => <li key={tool.registered_id}><strong>{tool.label}</strong><code>{tool.registered_id}</code><span>v{tool.version}</span></li>)}</ul> : <p className="muted">没有自动选择工具。</p>}
        </div>
        <div>
          <h3>Candidate retrieval</h3>
          {candidates.length ? <ul className="candidate-list">{candidates.map((tool) => <li key={tool.registered_id}><code>{tool.registered_id}</code><span>{Math.round((tool.retrieval_score ?? 0) * 100)}% match</span></li>)}</ul> : <p className="muted">没有匹配候选。</p>}
        </div>
      </div>

      <div className="rationale"><h3>Why this decision</h3><p>{summary.decision?.rationale ?? 'No rationale was returned.'}</p></div>
      <div className={`handling ${waiting ? 'handling-attention' : ''}`}><span>{waiting ? 'Human review required' : 'Error & handling'}</span><p>{summary.error_and_handling?.handling ?? 'No handling record was returned.'}</p></div>
    </section>
  );
}

function App() {
  const questionId = useId();
  const [state, setState] = useState(null);
  const [capabilities, setCapabilities] = useState(null);
  const [question, setQuestion] = useState('');
  const [inputTypes, setInputTypes] = useState([]);
  const [summary, setSummary] = useState(null);
  const [datasets, setDatasets] = useState([]);
  const [datasetDetail, setDatasetDetail] = useState(null);
  const [status, setStatus] = useState({ kind: 'loading', message: '正在读取 MatFlow 控制面…' });
  const [busy, setBusy] = useState(false);

  async function refreshControlPlane() {
    setStatus({ kind: 'loading', message: '正在刷新服务端状态…' });
    try {
      const [nextState, nextCapabilities, nextDatasets] = await Promise.all([request('/state'), request('/capabilities'), request('/uploads')]);
      setState(nextState);
      setCapabilities(nextCapabilities);
      setDatasets(nextDatasets.files ?? []);
      setStatus({ kind: 'ready', message: `已连接 · Graph v${nextState.state.version}` });
    } catch (error) {
      setStatus({ kind: 'error', message: error.message });
    }
  }

  useEffect(() => { refreshControlPlane(); }, []);

  function toggleInputType(type) {
    setInputTypes((current) => current.includes(type) ? current.filter((item) => item !== type) : [...current, type]);
  }

  async function routeTask(event) {
    event.preventDefault();
    if (!question.trim() || !state) return;
    setBusy(true);
    setStatus({ kind: 'loading', message: '正在请求服务端路由决策…' });
    try {
      const taskId = uniqueTaskId();
      const routed = await request('/route', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: { task_id: taskId, user_message: question.trim(), graph_version: state.state.version, available_input_types: inputTypes } }),
      });
      const persisted = await request(`/task-summaries/${encodeURIComponent(taskId)}`);
      setSummary(persisted ?? routed.summary);
      setStatus({ kind: routed.requires_human_confirmation ? 'attention' : 'ready', message: routed.requires_human_confirmation ? '路由等待人工确认' : '路由决策已保存' });
    } catch (error) {
      setStatus({ kind: 'error', message: error.message });
    } finally {
      setBusy(false);
    }
  }

  async function uploadDataset(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setStatus({ kind: 'loading', message: `正在导入 ${file.name}…` });
    try {
      const body = new FormData();
      body.append('files', file);
      const imported = await request('/uploads', { method: 'POST', body });
      const record = imported.files[0];
      setDatasetDetail(await request(`/uploads/${encodeURIComponent(record.id)}`));
      const listed = await request('/uploads');
      setDatasets(listed.files ?? []);
      setStatus({ kind: 'ready', message: `已导入 ${record.name}` });
    } catch (error) {
      setStatus({ kind: 'error', message: error.message });
    } finally {
      setBusy(false);
      event.target.value = '';
    }
  }

  async function inspectDataset(uploadId) {
    try {
      setDatasetDetail(await request(`/uploads/${encodeURIComponent(uploadId)}`));
    } catch (error) {
      setStatus({ kind: 'error', message: error.message });
    }
  }

  const registry = capabilities?.registry ?? state?.registry ?? {};
  const graph = state?.state;
  const dataTypes = capabilities?.data_types ?? state?.data_types ?? [];

  return (
    <div className="shell">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <header className="topbar">
        <a className="brand" href="#main-content" aria-label="MatFlow research workbench home"><span className="brand-mark" aria-hidden="true">M</span><span><strong>MatFlow</strong><small>materials research agent</small></span></a>
        <div className={`connection connection-${status.kind}`} role="status" aria-live="polite"><span aria-hidden="true" />{status.message}</div>
      </header>

      <div className="workspace">
        <aside className="evidence-sidebar" aria-label="Server confirmed workflow evidence">
          <section className="sidebar-section">
            <div className="eyebrow-row"><span>Graph state</span><button type="button" onClick={refreshControlPlane} disabled={busy}>Refresh</button></div>
            {graph ? <><strong className="graph-version">v{graph.version}</strong><p>{graph.nodes.length} nodes · {graph.edges.length} edges</p></> : <p>等待服务端状态。</p>}
            <div className="graph-summary" aria-label="Current graph summary">
              {graph?.nodes.length ? graph.nodes.map((node) => <div key={node.id}><span className={`node-dot node-${node.status}`} aria-hidden="true" /><strong>{node.label ?? node.type}</strong><code>{node.tool_id}</code></div>) : <p className="muted">当前图为空。路由不会自行修改它。</p>}
            </div>
          </section>

          <section className="sidebar-section registry-section">
            <div className="eyebrow-row"><span>Active registry</span><small>{Object.keys(registry).length} tools</small></div>
            <ul className="registry-list" tabIndex="0" aria-label="Active registry tools">{Object.entries(registry).map(([toolId, tool]) => <RegistryItem key={toolId} toolId={toolId} tool={tool} />)}</ul>
          </section>

          <section className="sidebar-section dataset-section">
            <div className="eyebrow-row"><span>Datasets</span><small>{datasets.length} files</small></div>
            <label className="dataset-upload">Import dataset<input type="file" onChange={uploadDataset} disabled={busy} accept=".csv,.txt,.xlsx,.xls,.json,.png,.jpg,.jpeg,.tif,.tiff" /></label>
            {datasets.length ? <ul className="dataset-list" aria-label="Imported datasets">{datasets.map((dataset) => <li className="registry-item" key={dataset.id}><button type="button" onClick={() => inspectDataset(dataset.id)}><strong>{dataset.name}</strong><span>{Math.ceil(dataset.size / 1024)} KB</span></button></li>)}</ul> : <p className="muted">尚未导入数据。</p>}
            {datasetDetail && <div className="dataset-detail"><strong>{datasetDetail.name}</strong><p>{datasetDetail.kind === 'table' ? `${datasetDetail.rows} rows · ${datasetDetail.columns.length} columns` : datasetDetail.kind}</p></div>}
          </section>

          <section className="sidebar-section feature-section">
            <span className="eyebrow">Feature flags</span>
            {Object.entries(capabilities?.features ?? {}).map(([feature, enabled]) => <p key={feature}><span className={enabled ? 'flag-on' : 'flag-off'} aria-hidden="true" />{feature.replaceAll('_', ' ')} <b>{enabled ? 'enabled' : 'disabled'}</b></p>)}
          </section>
        </aside>

        <main id="main-content" className="main-content">
          <section className="intro">
            <p className="kicker">A server-authoritative control plane</p>
            <h1>Research workbench</h1>
            <p>先提出研究任务，再查看 MatFlow 基于注册工具与当前输入作出的决策。图、工具兼容性和执行规则始终由后端确认。</p>
          </section>

          <section className="task-panel" aria-labelledby="task-heading">
            <div className="section-heading"><span className="section-index">01</span><div><h2 id="task-heading">Route a research task</h2><p>描述你想分析的材料数据，并声明目前可用的输入。</p></div></div>
            <form onSubmit={routeTask}>
              <label htmlFor={questionId}>研究问题 <span className="label-hint">Research question</span></label>
              <textarea id={questionId} aria-label="Research question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="例如：对已规范化的阻抗谱执行基础 EIS 质量检查" rows="4" required />
              <fieldset><legend>Available input types</legend><div className="input-type-grid">{dataTypes.map((type) => <label key={type} className="type-option"><input type="checkbox" checked={inputTypes.includes(type)} onChange={() => toggleInputType(type)} /><span>{type}</span></label>)}</div></fieldset>
              <div className="task-actions"><p>路由只生成决策和审计记录，不会自动执行工具或修改 GraphState。</p><button type="submit" disabled={busy || !question.trim() || !state}>{busy ? 'Routing…' : 'Get routing decision'}</button></div>
            </form>
          </section>

          <DecisionRecord summary={summary} />
        </main>
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
