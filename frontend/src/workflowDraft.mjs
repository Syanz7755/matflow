function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function same(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function safeId(value) {
  return String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'node';
}

export function createNodeFromTool(toolId, tool, graph, position = {}) {
  const taken = new Set((graph.nodes ?? []).map((node) => node.id));
  const base = safeId(toolId);
  let index = 1;
  while (taken.has(`${base}-${index}`)) index += 1;
  return {
    id: `${base}-${index}`,
    type: toolId,
    tool_id: toolId,
    tool_version: tool.version ?? '1.0.0',
    label: tool.label ?? toolId,
    params: clone(tool.params ?? {}),
    position: {
      x: Number.isFinite(position.x) ? position.x : 80 + ((graph.nodes?.length ?? 0) % 3) * 340,
      y: Number.isFinite(position.y) ? position.y : 80 + Math.floor((graph.nodes?.length ?? 0) / 3) * 230,
    },
    status: 'ready',
    output: null,
    preview: null,
    review_policy: { after_run: false, prompt: 'Review this result before continuing.' },
    review_state: { status: 'off', comment: null },
  };
}

export function normalizeImportedGraph(payload, registry = {}, currentVersion = 0) {
  const source = payload?.graph ?? payload;
  if (!source || !Array.isArray(source.nodes) || !Array.isArray(source.edges)) {
    throw new Error('The JSON file must contain graph.nodes and graph.edges arrays.');
  }

  const ids = new Set();
  const nodes = source.nodes.map((raw, index) => {
    if (!raw || typeof raw.id !== 'string' || typeof raw.type !== 'string') {
      throw new Error(`Node ${index + 1} must contain string id and type fields.`);
    }
    if (ids.has(raw.id)) throw new Error(`Duplicate node id: ${raw.id}`);
    ids.add(raw.id);
    const tool = registry[raw.type];
    if (!tool) throw new Error(`Unknown tool in imported workflow: ${raw.type}`);
    return {
      id: raw.id,
      type: raw.type,
      tool_id: raw.type,
      tool_version: tool.version ?? '1.0.0',
      label: typeof raw.label === 'string' && raw.label.trim() ? raw.label.trim() : tool.label,
      params: { ...clone(tool.params ?? {}), ...(raw.params && typeof raw.params === 'object' ? clone(raw.params) : {}) },
      position: {
        x: Number.isFinite(raw.position?.x) ? raw.position.x : 80 + (index % 3) * 340,
        y: Number.isFinite(raw.position?.y) ? raw.position.y : 80 + Math.floor(index / 3) * 230,
      },
      status: 'ready',
      output: null,
      preview: null,
      review_policy: {
        after_run: Boolean(raw.review_policy?.after_run),
        prompt: raw.review_policy?.prompt || 'Review this result before continuing.',
      },
      review_state: { status: 'off', comment: null },
    };
  });

  const edgeIds = new Set();
  const edges = source.edges.map((raw, index) => {
    const required = ['id', 'source', 'source_port', 'target', 'target_port'];
    if (!raw || required.some((key) => typeof raw[key] !== 'string' || !raw[key])) {
      throw new Error(`Edge ${index + 1} is missing an id, endpoint, or port.`);
    }
    if (edgeIds.has(raw.id)) throw new Error(`Duplicate edge id: ${raw.id}`);
    edgeIds.add(raw.id);
    return Object.fromEntries(required.map((key) => [key, raw[key]]));
  });

  return {
    graph_id: typeof source.graph_id === 'string' ? source.graph_id : 'local-default',
    version: currentVersion,
    nodes,
    edges,
    history: [],
  };
}

export function buildPatchOperations(saved = {}, draft = {}) {
  const savedNodes = new Map((saved.nodes ?? []).map((node) => [node.id, node]));
  const draftNodes = new Map((draft.nodes ?? []).map((node) => [node.id, node]));
  const replaced = new Set(
    [...savedNodes].filter(([id, node]) => draftNodes.has(id) && draftNodes.get(id).type !== node.type).map(([id]) => id),
  );
  const savedEdges = new Map((saved.edges ?? []).map((edge) => [edge.id, edge]));
  const draftEdges = new Map((draft.edges ?? []).map((edge) => [edge.id, edge]));
  const operations = [];

  for (const [id, edge] of savedEdges) {
    const next = draftEdges.get(id);
    if (!next || !same(edge, next) || replaced.has(edge.source) || replaced.has(edge.target)) {
      operations.push({ op: 'disconnect', edge_id: id });
    }
  }

  for (const [id, node] of savedNodes) {
    if (!draftNodes.has(id) || replaced.has(id)) operations.push({ op: 'delete_node', node_id: id });
  }

  for (const [id, node] of draftNodes) {
    if (!savedNodes.has(id) || replaced.has(id)) {
      operations.push({ op: 'add_node', node: clone(node) });
      continue;
    }
    const previous = savedNodes.get(id);
    const paramsChanged = !same(previous.params ?? {}, node.params ?? {});
    const labelChanged = (previous.label ?? null) !== (node.label ?? null);
    const positionChanged = !same(previous.position ?? {}, node.position ?? {});
    const reviewChanged = !same(previous.review_policy ?? { after_run: false, prompt: 'Review this result before continuing.' }, node.review_policy ?? { after_run: false, prompt: 'Review this result before continuing.' });
    if (paramsChanged || labelChanged || positionChanged || reviewChanged) {
      operations.push({
        op: 'update_node',
        node_id: id,
        ...(paramsChanged ? { params: clone(node.params ?? {}) } : {}),
        ...((labelChanged || positionChanged || reviewChanged) ? { changes: {
          ...(labelChanged ? { label: node.label ?? null } : {}),
          ...(positionChanged ? { position: clone(node.position) } : {}),
          ...(reviewChanged ? { review_policy: clone(node.review_policy) } : {}),
        } } : {}),
      });
    }
  }

  for (const [id, edge] of draftEdges) {
    const previous = savedEdges.get(id);
    if (!previous || !same(previous, edge) || replaced.has(edge.source) || replaced.has(edge.target)) {
      operations.push({ op: 'connect', edge: clone(edge) });
    }
  }
  return operations;
}

export function exportWorkflowDocument(graph) {
  return {
    format: 'matflow.workflow',
    format_version: '1.0',
    exported_at: new Date().toISOString(),
    graph: {
      graph_id: graph.graph_id ?? 'local-default',
      nodes: clone(graph.nodes ?? []).map(({ output: _output, preview: _preview, review_state: _reviewState, ...node }) => ({ ...node, status: 'ready' })),
      edges: clone(graph.edges ?? []),
    },
  };
}
