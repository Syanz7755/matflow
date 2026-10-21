#!/usr/bin/env node
// Fixed, reproducible agent evaluation for the 2026-10-20 acceptance package.
//
// For every case in evaluation/agent/agent_eval_cases.json and every repeat it:
//   1. resets the workspace and uploads the case fixtures
//   2. POST /api/route        (single-step path used by the WebUI decision panel)
//   3. POST /api/plan         (multi-step planner, apply=true so the typed patch is written)
//   4. GET  /api/state        (graph really applied: nodes/edges)
//   5. POST /api/workflow/execute (+ auto "continue" at review gates) for executable cases
// and scores five stages per case:
//   S1 plan status        S2 tool decomposition      S3 capability-gap flagging
//   S4 typed graph applied S5 execution + outputs
// plus route-path selection accuracy, per-stage pass rates, end-to-end success,
// cross-repeat stability, latency and (optionally) model tokens from the usage log.
//
//   node scripts/live_acceptance/eval_agent.mjs --repeats 3 \
//     --out docs/evaluation/agent/agent-eval.json --md docs/evaluation/agent/agent-eval.md
//
// Requires: the demo stack (scripts/start_demo.ps1) and, for tokens,
// MATFLOW_MODEL_USAGE_LOG set on the backend process.
import { readFile, readdir, stat, writeFile, mkdir } from 'node:fs/promises';
import { dirname, resolve, join } from 'node:path';

const ROOT = resolve(new URL('../..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'));
const API = process.env.MATFLOW_API ?? 'http://127.0.0.1:8000/api';
const USAGE_LOG = process.env.MATFLOW_MODEL_USAGE_LOG ?? join(ROOT, '.tmp/agent-eval/model-usage.jsonl');

function arg(name, fallback) {
  const index = process.argv.indexOf(`--${name}`);
  return index === -1 ? fallback : process.argv[index + 1];
}
const REPEATS = Number(arg('repeats', '3'));
const OUT_JSON = resolve(arg('out', 'docs/evaluation/agent/agent-eval.json'));
const OUT_MD = resolve(arg('md', 'docs/evaluation/agent/agent-eval.md'));
const CASES_FILE = resolve(arg('cases', 'evaluation/agent/agent_eval_cases.json'));
const LIMIT = Number(arg('limit', '0'));

const round = (value, digits = 2) => (value === null || value === undefined ? null : Number(value.toFixed(digits)));
const pct = (value) => (value === null ? 'n/a' : `${(value * 100).toFixed(1)}%`);

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers ?? {}) },
  });
  const text = await response.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = { raw: text }; }
  return { ok: response.ok, status: response.status, body };
}

async function timed(fn) {
  const started = process.hrtime.bigint();
  const value = await fn();
  return { value, latency_ms: Number(process.hrtime.bigint() - started) / 1e6 };
}

async function upload(filePath) {
  const absolute = resolve(ROOT, filePath);
  const bytes = await readFile(absolute);
  const form = new FormData();
  form.append('files', new Blob([bytes], { type: 'text/csv' }), absolute.split(/[\\/]/).pop());
  const response = await fetch(`${API}/uploads`, { method: 'POST', body: form });
  const body = await response.json();
  if (!response.ok) throw new Error(`upload failed for ${filePath}: ${response.status}`);
  return body.files[0];
}

async function usageSnapshot() {
  try {
    const info = await stat(USAGE_LOG);
    return { size: info.size };
  } catch {
    return { size: 0 };
  }
}

async function usageDelta(before) {
  try {
    const info = await stat(USAGE_LOG);
    if (info.size <= before.size) return { calls: 0, prompt_tokens: 0, completion_tokens: 0, total_tokens: null, latency_ms: 0 };
    const text = await readFile(USAGE_LOG, 'utf8');
    const lines = text.slice(before.size).split('\n').filter(Boolean);
    const rows = lines.map((line) => { try { return JSON.parse(line); } catch { return null; } }).filter(Boolean);
    const prompt = rows.reduce((sum, row) => sum + (row.prompt_tokens ?? 0), 0);
    const completion = rows.reduce((sum, row) => sum + (row.completion_tokens ?? 0), 0);
    return {
      calls: rows.length,
      prompt_tokens: prompt,
      completion_tokens: completion,
      total_tokens: prompt + completion,
      latency_ms: rows.reduce((sum, row) => sum + (row.latency_ms ?? 0), 0),
    };
  } catch {
    return null;
  }
}

function planTools(plan) {
  const tools = [];
  for (const action of plan.actions ?? []) {
    const tool = action?.node?.type ?? action?.tool_id ?? null;
    if (tool && tool !== 'skill_node') tools.push(tool);
    else if (tool === 'skill_node') tools.push(tool);
  }
  return [...new Set(tools)];
}

function gapFlagged(plan) {
  const issues = (plan.issues ?? []).join(' ');
  return /capability gap/i.test(issues) || ['clarify', 'refused'].includes(plan.status);
}

function routeSelected(route) {
  const selected = route?.selected ?? [];
  return selected.map((item) => item.tool_id).filter(Boolean);
}

async function runCase(spec, repeat) {
  await api('/reset?include_settings=false', { method: 'POST' });
  const uploads = [];
  for (const fixture of spec.fixtures ?? []) uploads.push(await upload(fixture));
  const attachments = uploads.map((item) => ({ upload_id: item.id, name: item.name, size: item.size, type: item.type }));

  const usageBefore = await usageSnapshot();

  // ---- single-step route path (WebUI decision panel)
  const route = await timed(() => api('/route', {
    method: 'POST',
    body: JSON.stringify({
      task: {
        task_id: `${spec.id}-r${repeat}`,
        user_message: spec.message,
        graph_version: 0,
        available_input_types: ['TypedTable'],
      },
    }),
  }));

  // ---- multi-step planner + applied graph
  const plan = await timed(() => api('/plan', {
    method: 'POST',
    body: JSON.stringify({ message: spec.message, task_id: `${spec.id}-r${repeat}`, attachments, apply: true }),
  }));

  const state = await api('/state');
  const graph = state.body?.state ?? { nodes: [], edges: [] };

  // ---- execution (auto-continue at review gates, at most 4 rounds)
  let execution = null;
  if (spec.executable) {
    const statuses = [];
    let last = null;
    for (let round = 0; round < 4; round += 1) {
      last = await api('/workflow/execute', { method: 'POST', body: JSON.stringify({ restart: round === 0 }) });
      if (!last.ok) break;
      const nodes = last.body?.state?.nodes ?? [];
      statuses.push(nodes.map((node) => `${node.id}:${node.status}`).join(' '));
      const waiting = nodes.find((node) => node.status === 'waiting');
      if (!waiting) break;
      await api('/workflow/decision', { method: 'POST', body: JSON.stringify({ node_id: waiting.id, decision: 'continue' }) });
    }
    const nodes = last?.body?.state?.nodes ?? [];
    const failed = nodes.filter((node) => node.status === 'failed');
    const completed = nodes.filter((node) => node.status === 'completed');
    execution = {
      ok: Boolean(last?.ok) && failed.length === 0 && nodes.length > 0 && completed.length === nodes.length,
      node_count: nodes.length,
      completed: completed.length,
      with_output: completed.filter((node) => node.output).length,
      statuses,
    };
  }

  const usage = await usageDelta(usageBefore);

  const planBody = plan.value.body ?? {};
  const tools = planTools(planBody);
  const required = spec.required_tools ?? [];
  const forbidden = spec.forbidden_tools ?? [];
  const selected = routeSelected(route.value.body);

  const stages = {
    S1_plan_status: (spec.plan_status ?? []).includes(planBody.status),
    S2_tool_decomposition: required.every((tool) => tools.includes(tool)) && forbidden.every((tool) => !tools.includes(tool)),
    S3_gap_flagging: spec.gap_required ? gapFlagged(planBody) : null,
    S4_typed_graph_applied: plan.value.ok && Array.isArray(graph.nodes) && graph.nodes.length > 0 && graph.edges.length >= Math.max(0, graph.nodes.length - 1),
    S5_execution: spec.executable ? Boolean(execution?.ok) : null,
  };
  if (!spec.executable) delete stages.S4_typed_graph_applied;

  let routeStage = null;
  if (spec.route_tool === 'skip') routeStage = null;
  else if (spec.route_tool === 'none') routeStage = selected.length === 0;
  else if (spec.route_tool === 'refuse') routeStage = route.value.body?.status === 'refused' || /refus/i.test(String(route.value.body?.decision?.rationale ?? ''));
  else routeStage = selected.includes(spec.route_tool);

  return {
    case_id: spec.id,
    class: spec.class,
    repeat,
    prompt: spec.message,
    plan: {
      status: planBody.status ?? null,
      tools,
      issues: planBody.issues ?? [],
      llm_calls: planBody.llm_calls ?? null,
      latency_ms: round(plan.latency_ms),
      http_ok: plan.value.ok,
    },
    route: {
      status: route.value.body?.status ?? null,
      selected,
      confidence: route.value.body?.decision?.confidence ?? null,
      requires_human_confirmation: route.value.body?.requires_human_confirmation ?? null,
      latency_ms: round(route.latency_ms),
      http_ok: route.value.ok,
    },
    graph: { nodes: graph.nodes?.length ?? 0, edges: graph.edges?.length ?? 0 },
    execution,
    usage,
    stages,
    route_stage: routeStage,
  };
}

function summarize(rows, cases) {
  const stageNames = ['S1_plan_status', 'S2_tool_decomposition', 'S3_gap_flagging', 'S4_typed_graph_applied', 'S5_execution'];
  const rate = (predicate) => {
    const considered = rows.filter(predicate);
    if (!considered.length) return { passed: 0, total: 0, rate: null };
    const passed = considered.filter((row) => Object.entries(row.stages).every(([, value]) => value === null || value === true)).length;
    return { passed, total: considered.length, rate: passed / considered.length };
  };
  const stage = {};
  for (const name of stageNames) {
    const considered = rows.filter((row) => row.stages[name] !== undefined && row.stages[name] !== null);
    stage[name] = considered.length
      ? { passed: considered.filter((row) => row.stages[name] === true).length, total: considered.length }
      : { passed: 0, total: 0 };
    stage[name].rate = stage[name].total ? stage[name].passed / stage[name].total : null;
  }

  const byCase = cases.map((spec) => {
    const caseRows = rows.filter((row) => row.case_id === spec.id);
    const stagePass = Object.fromEntries(stageNames.map((name) => {
      const considered = caseRows.filter((row) => row.stages[name] !== undefined && row.stages[name] !== null);
      return [name, considered.length ? considered.filter((row) => row.stages[name] === true).length : null];
    }));
    const stageApplied = Object.fromEntries(stageNames.map((name) => [
      name,
      caseRows.filter((row) => row.stages[name] !== undefined && row.stages[name] !== null).length,
    ]));
    const stabilityKey = (row) => JSON.stringify({
      status: row.plan.status,
      tools: row.plan.tools,
      stages: row.stages,
      route: row.route.selected,
    });
    const keys = new Set(caseRows.map(stabilityKey));
    return {
      case_id: spec.id,
      class: spec.class,
      repeats: caseRows.length,
      stages: stagePass,
      stage_applied: stageApplied,
      e2e: rate((row) => row.case_id === spec.id),
      route_stage: caseRows.filter((row) => row.route_stage === true).length,
      route_total: caseRows.filter((row) => row.route_stage !== null).length,
      stable: keys.size === 1,
      distinct_outcomes: keys.size,
      tools_seen: [...new Set(caseRows.flatMap((row) => row.plan.tools))],
      route_selected_seen: [...new Set(caseRows.flatMap((row) => row.route.selected))],
      latency_ms: { plan: round(median(caseRows.map((row) => row.plan.latency_ms))), route: round(median(caseRows.map((row) => row.route.latency_ms))) },
      tokens: {
        total: caseRows.reduce((sum, row) => sum + (row.usage?.total_tokens ?? 0), 0),
        calls: caseRows.reduce((sum, row) => sum + (row.usage?.calls ?? 0), 0),
      },
    };
  });

  const allLatency = rows.map((row) => row.plan.latency_ms).sort((a, b) => a - b);
  const routeLatency = rows.map((row) => row.route.latency_ms).sort((a, b) => a - b);
  const tokens = rows.reduce((sum, row) => sum + (row.usage?.total_tokens ?? 0), 0);
  const calls = rows.reduce((sum, row) => sum + (row.usage?.calls ?? 0), 0);

  const routeRows = rows.filter((row) => row.route_stage !== null);
  return {
    generated_at: new Date().toISOString(),
    repeats: REPEATS,
    cases: cases.length,
    observations: rows.length,
    stages: stage,
    e2e: rate(() => true),
    e2e_by_class: Object.fromEntries([...new Set(cases.map((spec) => spec.class))].map((cls) => [cls, rate((row) => row.class === cls)])),
    route_accuracy: { passed: routeRows.filter((row) => row.route_stage).length, total: routeRows.length, rate: routeRows.length ? routeRows.filter((row) => row.route_stage).length / routeRows.length : null },
    stability: {
      stable_cases: byCase.filter((item) => item.stable).length,
      total_cases: byCase.length,
      per_case: byCase.map((item) => ({ case_id: item.case_id, stable: item.stable, distinct_outcomes: item.distinct_outcomes })),
    },
    latency_ms: {
      plan: { mean: round(allLatency.reduce((sum, value) => sum + value, 0) / Math.max(1, allLatency.length)), p50: round(median(allLatency)), p90: round(percentile(allLatency, 0.9)) },
      route: { mean: round(routeLatency.reduce((sum, value) => sum + value, 0) / Math.max(1, routeLatency.length)), p50: round(median(routeLatency)), p90: round(percentile(routeLatency, 0.9)) },
    },
    tokens: { total: tokens, prompt: rows.reduce((sum, row) => sum + (row.usage?.prompt_tokens ?? 0), 0), completion: rows.reduce((sum, row) => sum + (row.usage?.completion_tokens ?? 0), 0), model_calls: calls, per_observation: round(tokens / Math.max(1, rows.length)) },
    failures: rows.filter((row) => Object.values(row.stages).some((value) => value === false))
      .map((row) => ({
        case_id: row.case_id,
        repeat: row.repeat,
        failed_stages: Object.entries(row.stages).filter(([, value]) => value === false).map(([name]) => name),
        plan_status: row.plan.status,
        tools: row.plan.tools,
        issues: (row.plan.issues ?? []).slice(0, 3),
        route_selected: row.route.selected,
      })),
    per_case: byCase,
  };
}

function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}
function percentile(values, ratio) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor(ratio * sorted.length))];
}

function renderMarkdown(summary) {
  const stageLabels = {
    S1_plan_status: 'S1 计划状态正确',
    S2_tool_decomposition: 'S2 工具分解正确',
    S3_gap_flagging: 'S3 能力缺口标注',
    S4_typed_graph_applied: 'S4 类型化图落盘',
    S5_execution: 'S5 执行与产出',
  };
  const lines = [];
  lines.push('# Agent 评测 · 固定测试集');
  lines.push('');
  lines.push(`生成时间：${summary.generated_at}`);
  lines.push(`测试集：\`evaluation/agent/agent_eval_cases.json\`（${summary.cases} 个 case × ${summary.repeats} 次重复 = ${summary.observations} 次观测）`);
  lines.push('');
  lines.push('## 分步正确率（plan 路径）');
  lines.push('');
  lines.push('| 阶段 | 通过 | 总数 | 正确率 |');
  lines.push('|---|---|---|---|');
  for (const [name, label] of Object.entries(stageLabels)) {
    const item = summary.stages[name];
    if (!item || !item.total) continue;
    lines.push(`| ${label} | ${item.passed} | ${item.total} | ${pct(item.rate)} |`);
  }
  lines.push('');
  lines.push('## 端到端 vs 分步');
  lines.push('');
  lines.push(`- 端到端成功率（所有适用阶段全过）：**${pct(summary.e2e.rate)}**（${summary.e2e.passed}/${summary.e2e.total}）`);
  for (const [cls, item] of Object.entries(summary.e2e_by_class)) {
    lines.push(`  - ${cls}: ${pct(item.rate)}（${item.passed}/${item.total}）`);
  }
  lines.push(`- 单步路由路径工具选择准确率：**${pct(summary.route_accuracy.rate)}**（${summary.route_accuracy.passed}/${summary.route_accuracy.total}）`);
  lines.push('');
  lines.push('## 可复现性（同一输入重复运行）');
  lines.push('');
  lines.push(`- 结果完全一致的 case：**${summary.stability.stable_cases}/${summary.stability.total_cases}**`);
  for (const item of summary.stability.per_case) {
    lines.push(`  - ${item.case_id}: ${item.stable ? '稳定' : `不稳定（${item.distinct_outcomes} 种结果）`}`);
  }
  lines.push('');
  lines.push('## 延迟与成本');
  lines.push('');
  lines.push('| 路径 | 均值 | p50 | p90 |');
  lines.push('|---|---|---|---|');
  lines.push(`| plan（多步规划） | ${summary.latency_ms.plan.mean} ms | ${summary.latency_ms.plan.p50} ms | ${summary.latency_ms.plan.p90} ms |`);
  lines.push(`| route（单步路由） | ${summary.latency_ms.route.mean} ms | ${summary.latency_ms.route.p50} ms | ${summary.latency_ms.route.p90} ms |`);
  lines.push('');
  lines.push(`- 模型调用：${summary.tokens.model_calls} 次；tokens 合计 ${summary.tokens.total}（prompt ${summary.tokens.prompt} / completion ${summary.tokens.completion}），平均每次观测 ${summary.tokens.per_observation}`);
  lines.push('- 金额：未换算 —— 需要 provider 单价；token 数已是可直接乘单价的原始量。');
  lines.push('');
  lines.push('## 逐 case');
  lines.push('');
  lines.push('| case | 类别 | S1 | S2 | S3 | S4 | S5 | 端到端 | route | 稳定 | plan tools（去重） |');
  lines.push('|---|---|---|---|---|---|---|---|---|---|---|');
  for (const item of summary.per_case) {
    const mark = (value, applied) => (value === undefined || value === null ? '·' : `${value}/${applied}`);
    const applied = (name) => item.stage_applied[name] || item.repeats;
    lines.push(`| ${item.case_id} | ${item.class} | ${mark(item.stages.S1_plan_status, applied('S1_plan_status'))} | ${mark(item.stages.S2_tool_decomposition, applied('S2_tool_decomposition'))} | ${mark(item.stages.S3_gap_flagging, applied('S3_gap_flagging'))} | ${mark(item.stages.S4_typed_graph_applied, applied('S4_typed_graph_applied'))} | ${mark(item.stages.S5_execution, applied('S5_execution'))} | ${pct(item.e2e.rate)} | ${item.route_total ? `${item.route_stage}/${item.route_total}` : '·'} | ${item.stable ? '是' : '否'} | ${item.tools_seen.join(' + ') || '—'} |`);
  }
  lines.push('');
  lines.push('## 失败观测');
  lines.push('');
  if (!summary.failures.length) lines.push('无。');
  for (const item of summary.failures.slice(0, 40)) {
    lines.push(`- ${item.case_id} #${item.repeat}: ${item.failed_stages.join(', ')} · plan=${item.plan_status} · tools=[${item.tools.join(', ')}] · route=[${item.route_selected.join(', ')}]`);
    if (item.issues?.length) lines.push(`  - issues: ${item.issues.join(' | ')}`);
  }
  lines.push('');
  lines.push('## 读数说明');
  lines.push('');
  lines.push('- S1–S5 对应“计划状态 / 工具分解 / 能力缺口标注 / 类型化图落盘 / 执行与产出”，分步正确率用于定位失败环节。');
  lines.push('- plan 路径 = `POST /api/plan`（多步规划，`apply=true` 让类型化补丁真正落盘）；route 路径 = `POST /api/route`（WebUI 决策面板用的单步路径）。');
  lines.push('- 端到端 = 该 case 适用的所有阶段均通过；类别 `gap`/`clarify`/`safety` 不适用 S4/S5。');
  lines.push('- 稳定 = 同一 case 的多次重复在“计划状态 + 工具集合 + 各阶段结果 + route 选择”上完全一致。');
  lines.push('- token 数来自后端 `MATFLOW_MODEL_USAGE_LOG` 记录（仅插桩，默认关闭）。');
  return lines.join('\n');
}

async function main() {
  const spec = JSON.parse(await readFile(CASES_FILE, 'utf8'));
  const cases = LIMIT ? spec.cases.slice(0, LIMIT) : spec.cases;
  const FROM = arg('from', '');
  let rows = [];
  if (FROM) {
    // Re-score a previous observation file without new model calls (scoring rules only).
    const saved = JSON.parse(await readFile(resolve(FROM), 'utf8'));
    const byId = new Map(cases.map((item) => [item.id, item]));
    rows = saved.rows.filter((row) => byId.has(row.case_id));
    for (const row of rows) {
      const item = byId.get(row.case_id);
      if (!item.gap_required) row.stages.S3_gap_flagging = null;
      if (!item.executable) {
        row.stages.S5_execution = null;
        delete row.stages.S4_typed_graph_applied;
      }
    }
    console.log(`· re-scored ${rows.length} saved observations from ${FROM}`);
  } else {
    for (const item of cases) {
      for (let repeat = 1; repeat <= REPEATS; repeat += 1) {
        process.stdout.write(`· ${item.id} #${repeat}\n`);
        try {
          rows.push(await runCase(item, repeat));
        } catch (error) {
          rows.push({
            case_id: item.id, class: item.class, repeat, prompt: item.message,
            plan: { status: null, tools: [], issues: [], latency_ms: null, http_ok: false, error: String(error) },
            route: { status: null, selected: [], latency_ms: null, http_ok: false },
            graph: { nodes: 0, edges: 0 }, execution: null, usage: null,
            stages: { S1_plan_status: false, S2_tool_decomposition: false, S3_gap_flagging: item.gap_required ? false : null, S4_typed_graph_applied: false, S5_execution: item.executable ? false : null },
            route_stage: null,
          });
        }
      }
    }
  }
  const summary = summarize(rows, cases);
  await mkdir(dirname(OUT_JSON), { recursive: true });
  await writeFile(OUT_JSON, JSON.stringify({ spec: { cases_file: CASES_FILE, repeats: REPEATS }, summary, rows }, null, 2));
  await writeFile(OUT_MD, renderMarkdown(summary));
  console.log(JSON.stringify({ stages: summary.stages, e2e: summary.e2e, route: summary.route_accuracy, latency: summary.latency_ms, tokens: summary.tokens, stability: summary.stability.stable_cases }, null, 2));
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
