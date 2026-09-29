function issue(code, message, details = {}) {
  return { code, message, ...details };
}

function detectCycle(nodes, edges) {
  const adjacency = new Map(nodes.map((node) => [node.id, []]));
  for (const edge of edges) adjacency.get(edge.source)?.push(edge.target);

  const visiting = new Set();
  const visited = new Set();

  function visit(nodeId) {
    if (visiting.has(nodeId)) return true;
    if (visited.has(nodeId)) return false;
    visiting.add(nodeId);
    for (const targetId of adjacency.get(nodeId) ?? []) {
      if (visit(targetId)) return true;
    }
    visiting.delete(nodeId);
    visited.add(nodeId);
    return false;
  }

  return nodes.some((node) => visit(node.id));
}

export function canDataTypeFlow(sourceType, targetType, definitions = {}) {
  if (sourceType === targetType) return true;
  const seen = new Set();
  const pending = [...(definitions[targetType]?.parents ?? [])];
  while (pending.length) {
    const current = pending.shift();
    if (current === sourceType) return true;
    if (seen.has(current)) continue;
    seen.add(current);
    pending.push(...(definitions[current]?.parents ?? []));
  }
  return false;
}

function resolvedPorts(spec = {}, node = {}) {
  if (!spec.abstract) return { inputs: spec.inputs ?? {}, outputs: spec.outputs ?? {} };
  if (node.type !== 'type_cast') return { inputs: {}, outputs: {} };
  const sourceType = node.params?.source_type;
  const targetType = node.params?.target_type;
  return {
    inputs: sourceType ? { value: sourceType } : {},
    outputs: targetType ? { value: targetType } : {},
  };
}

export function buildWorkflowGraphModel(graph = {}, registry = {}, dataTypeDefinitions = {}) {
  const rawNodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  const rawEdges = Array.isArray(graph.edges) ? graph.edges : [];
  const issues = [];
  const nodeIds = new Set();

  for (const node of rawNodes) {
    if (nodeIds.has(node.id)) {
      issues.push(issue('duplicate_node', `Node ID “${node.id}” appears more than once.`, { nodeId: node.id }));
    }
    nodeIds.add(node.id);
    if (!registry[node.type]) {
      issues.push(issue('unknown_tool', `Node “${node.id}” references unknown tool “${node.type}”.`, { nodeId: node.id }));
    }
  }

  const nodes = rawNodes.map((node, index) => {
    const spec = registry[node.type] ?? {};
    const ports = resolvedPorts(spec, node);
    const inputs = Object.entries(ports.inputs).map(([id, dataType]) => ({ id, dataType }));
    const outputs = Object.entries(ports.outputs).map(([id, dataType]) => ({ id, dataType }));
    return {
      id: node.id,
      type: 'workflowNode',
      position: {
        x: Number.isFinite(node.position?.x) ? node.position.x : 80 + index * 340,
        y: Number.isFinite(node.position?.y) ? node.position.y : 100 + (index % 2) * 220,
      },
      data: {
        label: node.label ?? spec.label ?? node.type,
        toolId: node.tool_id ?? node.type,
        toolVersion: node.tool_version ?? spec.version ?? '1.0.0',
        category: spec.category ?? 'Unknown',
        status: node.status ?? 'ready',
        inputs,
        outputs,
      },
    };
  });

  const edgeIds = new Set();
  const occupiedInputs = new Set();
  const validEdges = [];

  for (const edge of rawEdges) {
    let valid = true;
    if (edgeIds.has(edge.id)) {
      issues.push(issue('duplicate_edge', `Edge ID “${edge.id}” appears more than once.`, { edgeId: edge.id }));
      valid = false;
    }
    edgeIds.add(edge.id);

    const source = rawNodes.find((node) => node.id === edge.source);
    const target = rawNodes.find((node) => node.id === edge.target);
    if (!source || !target) {
      issues.push(issue('missing_node', `Edge “${edge.id}” references a missing node.`, { edgeId: edge.id }));
      valid = false;
    } else {
      const sourceType = resolvedPorts(registry[source.type], source).outputs[edge.source_port];
      const targetType = resolvedPorts(registry[target.type], target).inputs[edge.target_port];
      if (!sourceType || !targetType) {
        issues.push(issue('unknown_port', `Edge “${edge.id}” references an unknown port.`, { edgeId: edge.id }));
        valid = false;
      } else if (!canDataTypeFlow(sourceType, targetType, dataTypeDefinitions)) {
        issues.push(issue('type_mismatch', `Edge “${edge.id}” connects ${sourceType} to ${targetType}.`, { edgeId: edge.id }));
        valid = false;
      }

      const inputKey = `${edge.target}:${edge.target_port}`;
      if (occupiedInputs.has(inputKey)) {
        issues.push(issue('occupied_input', `Input “${edge.target}.${edge.target_port}” has more than one connection.`, { edgeId: edge.id }));
        valid = false;
      }
      occupiedInputs.add(inputKey);
    }

    if (valid) {
      validEdges.push({
        id: edge.id,
        source: edge.source,
        sourceHandle: edge.source_port,
        target: edge.target,
        targetHandle: edge.target_port,
        type: 'default',
        animated: false,
        ariaLabel: `${edge.source}.${edge.source_port} to ${edge.target}.${edge.target_port}`,
        markerEnd: { type: 'arrowclosed', width: 18, height: 18, color: '#55738d' },
        style: { strokeWidth: 2.25 },
      });
    }
  }

  if (detectCycle(rawNodes, validEdges)) {
    issues.push(issue('cycle', 'The graph contains a directed cycle.'));
  }

  return { nodes, edges: validEdges, issues };
}
