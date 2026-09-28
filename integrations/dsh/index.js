import { lstat, readFile, realpath } from 'node:fs/promises';
import { basename, resolve, sep } from 'node:path';

export const name = 'matflow-dsh-integration';
export const inject = ['tools', 'systemPrompt', 'approval'];

const READ_TOOLS = new Set([
  'get_workspace_state',
  'inspect_dataset',
  'route_research_task',
  'validate_graph_patch',
  'get_task_summary',
]);
const WRITE_TOOLS = new Set([
  'import_dataset',
  'apply_graph_patch',
  'execute_workflow',
  'submit_human_decision',
]);

function within(path, root) {
  const prefix = root.endsWith(sep) ? root : `${root}${sep}`;
  return path === root || path.startsWith(prefix);
}

async function safeLocalFile(input, roots) {
  const requested = resolve(input);
  const stat = await lstat(requested);
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error('Only regular, non-symlink files can be imported.');
  }
  const actual = await realpath(requested);
  const allowed = await Promise.all(roots.map(async (root) => realpath(resolve(root)).catch(() => resolve(root))));
  if (!allowed.some((root) => within(actual, root))) {
    throw new Error(`File is outside the allowed DSH workspace and attachment roots: ${actual}`);
  }
  if (stat.size > 25 * 1024 * 1024) throw new Error('File exceeds the 25 MB MatFlow limit.');
  return { actual, stat };
}

export function apply(ctx, config = {}) {
  const apiBaseUrl = String(config.apiBaseUrl ?? 'http://127.0.0.1:8000').replace(/\/$/, '');
  const dshHome = process.env.DSH_HOME ?? resolve(process.env.USERPROFILE ?? process.cwd(), '.dsh');
  const roots = [process.cwd(), resolve(dshHome, 'attachments', 'v1', 'files'), ...(config.allowedRoots ?? [])];

  ctx.systemPrompt.section({
    name: 'matflow:mcp-policy',
    order: 460,
    text: [
      'MatFlow is the authoritative materials-workflow workspace.',
      'Inspect state and datasets before making claims. Validate graph patches before applying them.',
      'Import, graph mutation, execution, and human-decision tools require the user approval shown by this client.',
      'Never invent file contents, observations, tool success, or workflow outputs.',
    ].join(' '),
  });

  ctx.on('tools/pre-execute', async (exec, next) => {
    if (exec.name === 'matflow_import_local_dataset') {
      return { kind: 'ask', reason: 'Import this local file into the MatFlow workspace?' };
    }
    if (!exec.name.startsWith('mcp__matflow__')) return next();
    const rawName = exec.name.slice('mcp__matflow__'.length);
    if (READ_TOOLS.has(rawName)) return next();
    if (WRITE_TOOLS.has(rawName)) {
      return { kind: 'ask', reason: `Allow MatFlow write or execution tool ${rawName}?` };
    }
    return { kind: 'ask', reason: `Allow unclassified MatFlow tool ${rawName}?` };
  }, { prepend: true });

  ctx.tools.register({
    name: 'matflow_import_local_dataset',
    description: 'Import one local DSH workspace or attachment file into MatFlow. Requires approval.',
    parameters: {
      type: 'object',
      additionalProperties: false,
      required: ['path'],
      properties: {
        path: { type: 'string', minLength: 1, description: 'Absolute or workspace-relative local file path.' },
      },
    },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
    },
    async execute(args, exec) {
      const { actual } = await safeLocalFile(args.path, roots);
      const bytes = await readFile(actual);
      const form = new FormData();
      form.append('files', new Blob([bytes]), basename(actual));
      const response = await fetch(`${apiBaseUrl}/api/uploads`, { method: 'POST', body: form, signal: exec.signal });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail ?? `MatFlow upload failed with HTTP ${response.status}`);
      return payload;
    },
    presentCall: (args) => ({ card: 'generic', title: `Import ${basename(args.path)} into MatFlow`, kind: 'execute', rawInput: args.path }),
  });
}
