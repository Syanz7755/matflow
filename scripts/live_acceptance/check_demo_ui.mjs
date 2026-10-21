#!/usr/bin/env node
// Health-check the MatFlow WebUI in the order the demo video records it.
//
// Drives the real UI (no mocks) through the 10 storyboard scenes plus the
// optional stop-run / export-import branches, asserts what the recording
// tutorial promises on screen and over the API, and reports PASS / FAIL /
// KNOWN (a documented deviation reproduced on purpose).
//
// Preconditions: backend + WebUI running, workspace empty (fresh save).
// Docs: docs/acceptance/2026-10-20-live/demo-tutorial/DEMO_TUTORIAL.zhcn.md
//
// Environment:
//   MATFLOW_WEB_URL        WebUI URL              (default http://127.0.0.1:5173/)
//   MATFLOW_API            API base, with /api   (default http://127.0.0.1:8000/api)
//   MATFLOW_FRONTEND_REPO  frontend checkout with playwright installed (default ../matflow-frontend)
//   MATFLOW_DEMO_CSV       dataset to import     (default examples/data/01_eis_basic_qc/eis_spectrum.csv)
//   MATFLOW_HEALTH_EVIDENCE evidence JSON path   (default docs/acceptance/2026-10-20-live/demo-tutorial/health-check.json)
//   MATFLOW_HEALTH_SHOTS   failure screenshot dir (default .tmp/health)
//   MATFLOW_VIEWPORT       WxH                   (default 1920x1080)
//
// Exit codes: 0 = no FAIL (KNOWN is allowed), 1 = at least one FAIL, 2 = precondition failed.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '..', '..');

const WEB_URL = process.env.MATFLOW_WEB_URL ?? 'http://127.0.0.1:5173/';
const API = (process.env.MATFLOW_API ?? 'http://127.0.0.1:8000/api').replace(/\/$/, '');
const DOCS_URL = API.replace(/\/api$/, '') + '/docs';
const FRONTEND = path.resolve(process.env.MATFLOW_FRONTEND_REPO ?? path.join(repo, '..', 'matflow-frontend'));
const CSV = path.resolve(process.env.MATFLOW_DEMO_CSV ?? path.join(repo, 'examples', 'data', '01_eis_basic_qc', 'eis_spectrum.csv'));
const EVIDENCE = path.resolve(process.env.MATFLOW_HEALTH_EVIDENCE ?? path.join(repo, 'docs', 'acceptance', '2026-10-20-live', 'demo-tutorial', 'health-check.json'));
const SHOTS = path.resolve(process.env.MATFLOW_HEALTH_SHOTS ?? path.join(repo, '.tmp', 'health'));
const ROUTE_PROMPT = '请对这份电化学阻抗谱数据做基本质控：检查高频段虚部符号是否为负、低频段是否发散，并给出质控结论。';
const [viewWidth, viewHeight] = (process.env.MATFLOW_VIEWPORT ?? '1920x1080').split('x').map(Number);
const STARTED_AT = new Date().toISOString();

const checks = [];
const log = [];
const step = (message) => { log.push({ at: new Date().toISOString(), message }); console.log('·', message); };

function fail(message, code = 1) {
  const error = new Error(message);
  error.exitCode = code;
  throw error;
}
function must(ok, message) {
  if (!ok) throw new Error(message);
  return message;
}
const detailOf = (value) => {
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  return text.length > 220 ? `${text.slice(0, 217)}…` : text;
};

async function record(scene, id, name, run) {
  try {
    const detail = await run();
    checks.push({ scene, id, name, status: 'PASS', detail: detailOf(detail ?? '') });
    console.log(`  PASS ${id} ${name}`);
  } catch (error) {
    checks.push({ scene, id, name, status: 'FAIL', detail: detailOf(error.message) });
    console.log(`  FAIL ${id} ${name}: ${error.message}`);
    throw error;
  }
}
async function recordKnown(scene, id, name, run) {
  try {
    const detail = await run();
    checks.push({ scene, id, name, status: 'PASS', detail: detailOf(`unexpectedly healthy: ${detail ?? ''}`) });
    console.log(`  PASS ${id} ${name} (expected deviation did not reproduce)`);
  } catch (error) {
    checks.push({ scene, id, name, status: 'KNOWN', detail: detailOf(error.message) });
    console.log(`  KNOWN ${id} ${name}: ${error.message}`);
  }
}

async function loadPlaywright() {
  const candidates = [
    path.join(FRONTEND, 'node_modules', 'playwright', 'index.mjs'),
    path.join(FRONTEND, 'apps', 'webui', 'node_modules', 'playwright', 'index.mjs'),
  ];
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (!found) fail(`playwright was not found in the frontend checkout (${FRONTEND}); run npm install there, or set MATFLOW_FRONTEND_REPO.`, 2);
  return import(pathToFileURL(found).href);
}

async function main() {
  if (!fs.existsSync(CSV)) fail(`the demo dataset is missing: ${CSV}`, 2);
  const { chromium } = await loadPlaywright();
  fs.mkdirSync(SHOTS, { recursive: true });
  fs.mkdirSync(path.dirname(EVIDENCE), { recursive: true });

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: viewWidth, height: viewHeight }, acceptDownloads: true, deviceScaleFactor: 1 });
  const consoleErrors = [];
  const pageErrors = [];
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  page.on('pageerror', (error) => pageErrors.push(String(error)));

  const canvas = page.locator('[data-testid="workflow-canvas"]');
  const nodeByLabel = (label) => canvas.locator('article.workflow-node').filter({ hasText: label }).first();
  const nodeCount = () => canvas.locator('article.workflow-node').count();
  const edgeCount = () => canvas.locator('.react-flow__edge').count();
  const statusText = async () => (await page.locator('.connection').innerText()).trim();
  const noticeText = async () => (await page.locator('.editor-notice').innerText()).trim();
  const chipText = async () => (await page.locator('.graph-state-chip').innerText()).trim();
  const waitStatus = (fragment, timeout = 90000) => page.waitForFunction((text) => (document.querySelector('.connection')?.textContent ?? '').includes(text), fragment, { timeout });
  const waitNotice = (regex, timeout = 30000) => page.waitForFunction((source) => new RegExp(source).test(document.querySelector('.editor-notice')?.textContent ?? ''), regex.source, { timeout });
  const waitNodeStatus = (label, wanted, timeout = 90000) => page.waitForFunction(({ nodeLabel, nodeStatus }) => {
    const nodes = [...document.querySelectorAll('[data-testid="workflow-canvas"] article.workflow-node')];
    const node = nodes.find((candidate) => (candidate.getAttribute('aria-label') ?? '').startsWith(nodeLabel));
    return (node?.querySelector('.node-status')?.textContent ?? '').trim() === nodeStatus;
  }, { nodeLabel: label, nodeStatus: wanted }, { timeout });
  const nodeStatuses = () => page.evaluate(() => [...document.querySelectorAll('[data-testid="workflow-canvas"] article.workflow-node')].map((node) => ({
    label: node.querySelector('strong')?.textContent.trim() ?? '',
    status: node.querySelector('.node-status')?.textContent.trim() ?? '',
  })));
  const nodeStatus = async (label) => (await nodeStatuses()).find((entry) => entry.label === label)?.status ?? '';
  const api = async (endpoint) => {
    const response = await page.request.get(`${API}${endpoint}`);
    if (!response.ok()) fail(`${API}${endpoint} answered ${response.status()}`, 2);
    return response.json();
  };
  const readState = async () => (await api('/state')).state;
  const failureShot = async (label) => {
    const file = path.join(SHOTS, `${label}-${Date.now()}.png`);
    await page.screenshot({ path: file }).catch(() => {});
    return file;
  };

  const clickPort = async (label, portId) => {
    await nodeByLabel(label).locator(`.workflow-port[data-port-id="${portId}"]`).first().locator('.react-flow__handle').click({ force: true });
  };
  const openConnectMode = async (label, portId) => {
    for (let attempt = 1; attempt <= 3; attempt += 1) {
      await clickPort(label, portId);
      try { await page.locator('.connect-helper').waitFor({ timeout: 2000 }); return attempt; } catch {
        step(`connect mode did not open from ${label}.${portId} (attempt ${attempt}); retrying`);
        await page.keyboard.press('Escape');
        await page.waitForTimeout(250);
      }
    }
    throw new Error(`could not start a connection from ${label}.${portId}`);
  };
  const connectPorts = async (sourceLabel, sourcePort, targetLabel, targetPort) => {
    for (let attempt = 1; attempt <= 3; attempt += 1) {
      const count = await edgeCount();
      const modeAttempt = await openConnectMode(sourceLabel, sourcePort);
      await clickPort(targetLabel, targetPort);
      try {
        await page.waitForFunction((expected) => document.querySelectorAll('[data-testid="workflow-canvas"] .react-flow__edge').length === expected, count + 1, { timeout: 5000 });
        return `edges=${count + 1} (mode attempt ${modeAttempt})`;
      } catch {
        step(`connect ${sourcePort} -> ${targetPort} did not register (attempt ${attempt}); retrying`);
        await page.keyboard.press('Escape');
        await page.waitForTimeout(250);
      }
    }
    throw new Error(`could not connect ${sourcePort} -> ${targetPort}`);
  };
  const addTool = async (label) => {
    await page.locator('#library-tab').click();
    await page.locator('button.tool-card').filter({ hasText: label }).first().click();
    await page.waitForFunction((text) => [...document.querySelectorAll('article.workflow-node strong')].some((element) => element.textContent.trim() === text), label);
  };
  const selectNode = async (label, expectedId) => {
    await nodeByLabel(label).click();
    await page.waitForFunction((id) => (document.querySelector('.node-inspector .panel-title code')?.textContent ?? '').includes(id), expectedId, { timeout: 8000 });
  };
  const setParam = async (label, value) => {
    const field = page.locator('.inspector-params label.inspector-field').filter({ has: page.locator('span', { hasText: label }) }).first();
    await field.locator('input').fill(String(value));
    await field.locator('input').blur();
    return field.locator('input').inputValue();
  };
  const saveWorkflow = async () => {
    await page.locator('button[aria-label="Save workflow"]').click();
    await waitNotice(/Saved as graph|already saved/);
    return noticeText();
  };

  try {
    // ---------------- S0 empty workbench ----------------
    step('S0 loading the empty workbench');
    await page.goto(WEB_URL, { waitUntil: 'domcontentloaded' });
    await page.locator('.workflow-editor').waitFor({ timeout: 30000 });
    await waitStatus('Connected');
    await record('S0', 'S0-01', 'WebUI connects to the backend', async () => must((await statusText()) === 'Connected · Graph v0', `status="${await statusText()}"`));
    const initial = await readState();
    await record('S0', 'S0-02', 'Graph state panel shows v0 / 0 nodes / 0 edges', async () => {
      const body = (await page.locator('.sidebar-section').first().innerText()).replace(/\n/g, ' | ');
      must(body.includes('v0'), `panel="${body}"`);
      must(body.includes('0 nodes · 0 edges'), `panel="${body}"`);
      return body;
    });
    await record('S0', 'S0-03', 'Active registry lists 18 tools', async () => must((await page.locator('.registry-section small').innerText()).includes('18'), `registry count="${await page.locator('.registry-section small').innerText()}"`));
    await record('S0', 'S0-04', 'No dataset imported yet', async () => {
      must((await page.locator('.dataset-section small').innerText()).includes('0'), 'dataset count is not 0');
      must((await page.locator('.dataset-list').count()) === 0, 'dataset list is not empty');
      return 'datasets=0';
    });
    await record('S0', 'S0-05', 'Canvas is empty', async () => must((await nodeCount()) === 0, `nodes=${await nodeCount()}`));
    await record('S0', 'S0-06', 'Topbar exposes the three demo actions and QE is enabled on an empty graph', async () => {
      const buttons = page.locator('.topbar-actions button');
      must((await buttons.count()) === 3, `topbar buttons=${await buttons.count()}`);
      const qe = buttons.filter({ hasText: 'Run MgO QE replay demo' });
      must(!(await qe.isDisabled()), 'QE demo button is disabled on an empty workspace');
      return `buttons=${(await buttons.allInnerTexts()).join(' / ')}`;
    });
    await record('S0', 'S0-07', 'Feature flags render', async () => {
      const flags = await page.locator('.feature-section p').count();
      must(flags === 3, `feature flags=${flags}`);
      return `flags=${flags}`;
    });
    await record('S0', 'S0-08', 'Refresh re-reads server state', async () => {
      await page.locator('.eyebrow-row button', { hasText: 'Refresh' }).click();
      await waitStatus('Connected');
      return await statusText();
    });
    await record('S0', 'S0-09', 'Server reports an empty graph', async () => {
      must(initial.version === 0 && initial.nodes.length === 0 && initial.edges.length === 0, `v${initial.version} ${initial.nodes.length}/${initial.edges.length}`);
      return `v${initial.version}`;
    });

    // ---------------- S1 import dataset ----------------
    step('S1 importing the dataset');
    await record('S1', 'S1-01', 'Import dataset succeeds', async () => {
      await page.locator('label.dataset-upload input[type=file]').setInputFiles(CSV);
      await waitStatus('Imported', 30000);
      return await statusText();
    });
    await record('S1', 'S1-02', 'Dataset detail shows 13 rows x 3 columns', async () => {
      await page.locator('.dataset-detail').waitFor({ timeout: 30000 });
      const text = (await page.locator('.dataset-detail').innerText()).replace(/\n/g, ' | ');
      must(text.includes('13 rows · 3 columns'), `detail="${text}"`);
      return text;
    });
    await record('S1', 'S1-03', 'Clicking the dataset lists its columns', async () => {
      const item = page.locator('.dataset-list button').first();
      await item.click();
      await page.locator('.dataset-detail').waitFor({ timeout: 10000 });
      const uploads = (await api('/uploads')).files;
      must(uploads.length === 1, `uploads=${uploads.length}`);
      return `upload=${uploads[0].name}`;
    });

    // ---------------- S2 typed graph ----------------
    step('S2 building the typed graph');
    await record('S2', 'S2-01', 'Tool library adds three nodes', async () => {
      await addTool('Raw File Import');
      await addTool('Normalize / Column Mapping');
      await addTool('EIS Basic Analysis');
      must((await nodeCount()) === 3, `nodes=${await nodeCount()}`);
      return 'nodes=3';
    });
    await record('S2', 'S2-02', 'Nodes expose typed ports', async () => {
      await page.waitForFunction(() => [...document.querySelectorAll('[data-testid="workflow-canvas"] .port-type')].filter((element) => element.textContent.trim()).length >= 4, null, { timeout: 10000 });
      const ports = await page.evaluate(() => {
        const nodes = [...document.querySelectorAll('[data-testid="workflow-canvas"] article.workflow-node')];
        return nodes.map((node) => ({
          label: node.querySelector('strong')?.textContent.trim() ?? '',
          inputs: [...node.querySelectorAll('section[aria-label="Input ports"] .port-type')].map((element) => element.textContent.trim()),
          outputs: [...node.querySelectorAll('section[aria-label="Output ports"] .port-type')].map((element) => element.textContent.trim()),
        }));
      });
      const normalize = ports.find((entry) => entry.label.startsWith('Normalize'));
      const eis = ports.find((entry) => entry.label.startsWith('EIS Basic Analysis'));
      must(normalize?.inputs.includes('RawData') && normalize?.outputs.includes('TypedTable'), `normalize=${JSON.stringify(normalize)}`);
      must(eis?.inputs.includes('TypedTable') && eis?.outputs.includes('EISQCReport'), `eis=${JSON.stringify(eis)}`);
      return ports.map((entry) => `${entry.label}:${entry.inputs.join('+')}->${entry.outputs.join('+')}`).join(' | ');
    });
    await record('S2', 'S2-03', 'Raw File Import binds the imported dataset', async () => {
      await selectNode('Raw File Import', 'raw_file_import-1');
      const select = page.locator('.inspector-params select').first();
      await select.selectOption({ index: 1 });
      const value = await select.inputValue();
      must(value.length > 0, 'dataset select stayed empty');
      return `upload_id=${value}`;
    });
    await record('S2', 'S2-04', 'Typed port connections create two edges', async () => {
      const first = await connectPorts('Raw File Import', 'raw', 'Normalize / Column Mapping', 'raw');
      const second = await connectPorts('Normalize / Column Mapping', 'table', 'EIS Basic Analysis', 'data');
      must((await edgeCount()) === 2, `edges=${await edgeCount()}`);
      return `${first}; ${second}`;
    });
    await record('S2', 'S2-05', 'Draft is dirty and Discard draft changes is enabled', async () => {
      const chip = await chipText();
      must(/unsaved change/.test(chip), `chip="${chip}"`);
      const discard = page.locator('button[aria-label="Discard draft changes"]');
      must(!(await discard.isDisabled()), 'discard is disabled while the draft is dirty');
      return chip;
    });
    await record('S2', 'S2-06', 'Discard draft changes resets the canvas', async () => {
      await page.locator('button[aria-label="Discard draft changes"]').click();
      await page.waitForFunction(() => document.querySelectorAll('[data-testid="workflow-canvas"] article.workflow-node').length === 0, null, { timeout: 8000 });
      const notice = await noticeText();
      must(notice.includes('Draft changes discarded.'), `notice="${notice}"`);
      return `${await chipText()}; ${notice}`;
    });
    await record('S2', 'S2-07', 'Rebuilt graph still connects after the discard', async () => {
      await addTool('Raw File Import');
      await page.locator('.inspector-params select').first().selectOption({ index: 1 });
      await addTool('Normalize / Column Mapping');
      await addTool('EIS Basic Analysis');
      await connectPorts('Raw File Import', 'raw', 'Normalize / Column Mapping', 'raw');
      await connectPorts('Normalize / Column Mapping', 'table', 'EIS Basic Analysis', 'data');
      must((await nodeCount()) === 3 && (await edgeCount()) === 2, `nodes=${await nodeCount()} edges=${await edgeCount()}`);
      return 'nodes=3 edges=2';
    });
    await record('S2', 'S2-08', 'Node action menu renames a node', async () => {
      await nodeByLabel('EIS Basic Analysis').locator('button.node-menu-button').click();
      await page.locator('.node-context-menu button', { hasText: 'Rename node' }).click();
      await page.locator('#node-label').fill('EIS QC renamed');
      await page.locator('.rename-dialog button[type=submit]').click();
      await page.waitForFunction(() => [...document.querySelectorAll('article.workflow-node strong')].some((element) => element.textContent.trim() === 'EIS QC renamed'));
      await nodeByLabel('EIS QC renamed').locator('button.node-menu-button').click();
      await page.locator('.node-context-menu button', { hasText: 'Rename node' }).click();
      await page.locator('#node-label').fill('EIS Basic Analysis');
      await page.locator('.rename-dialog button[type=submit]').click();
      await page.waitForFunction(() => [...document.querySelectorAll('article.workflow-node strong')].some((element) => element.textContent.trim() === 'EIS Basic Analysis'));
      return await noticeText();
    });

    // ---------------- S3 parameters, review, save ----------------
    step('S3 editing parameters, enabling review and saving');
    await record('S3', 'S3-01', 'Inspector edits the three column parameters', async () => {
      await selectNode('EIS Basic Analysis', 'eis_basic_qc-1');
      const frequency = await setParam('frequency column', 'frequency_hz');
      const real = await setParam('real column', 'z_real_ohm');
      const imag = await setParam('imag column', 'z_imag_ohm');
      return `${frequency}/${real}/${imag}`;
    });
    await record('S3', 'S3-02', 'Review toggle turns on', async () => {
      const toggle = nodeByLabel('EIS Basic Analysis').locator('label.node-review-toggle input');
      await toggle.check();
      must(await toggle.isChecked(), 'review checkbox is not checked');
      return 'review=on';
    });
    await record('S3', 'S3-03', 'Save creates Graph v1', async () => {
      const notice = await saveWorkflow();
      must(notice.includes('Saved as graph v1.'), `notice="${notice}"`);
      must((await chipText()).includes('Saved · Graph v1'), `chip="${await chipText()}"`);
      return await statusText();
    });
    await record('S3', 'S3-04', 'Server persisted nodes, edges, params and review policy', async () => {
      const state = await readState();
      const eis = state.nodes.find((node) => node.type === 'eis_basic_qc');
      must(state.nodes.length === 3 && state.edges.length === 2, `nodes=${state.nodes.length} edges=${state.edges.length}`);
      must(eis.params.frequency_column === 'frequency_hz' && eis.params.real_column === 'z_real_ohm' && eis.params.imag_column === 'z_imag_ohm', `params=${JSON.stringify(eis.params)}`);
      must(eis.review_policy?.after_run === true, 'review policy was not persisted');
      return `v${state.version} review=true`;
    });
    await record('S3', 'S3-05', 'Save button disables when the draft is clean', async () => {
      must(await page.locator('button[aria-label="Save workflow"]').isDisabled(), 'save is still enabled after saving');
      return 'save=disabled';
    });

    // ---------------- S4 run to the review gate ----------------
    step('S4 running to the human review gate');
    await record('S4', 'S4-01', 'Run pauses at the EIS review gate', async () => {
      await page.locator('button[aria-label="Run workflow from start"]').click();
      await waitNodeStatus('EIS Basic Analysis', 'Waiting');
      must((await statusText()).includes('paused for human review'), `status="${await statusText()}"`);
      return await statusText();
    });
    await record('S4', 'S4-02', 'Upstream nodes completed and the gate offers three actions', async () => {
      const raw = await nodeStatus('Raw File Import');
      const normalize = await nodeStatus('Normalize / Column Mapping');
      must(raw === 'Completed' && normalize === 'Completed', `raw=${raw} normalize=${normalize}`);
      await selectNode('EIS Basic Analysis', 'eis_basic_qc-1');
      await page.locator('.decision-actions').waitFor({ timeout: 10000 });
      const labels = (await page.locator('.decision-actions button').allInnerTexts()).map((value) => value.trim());
      must(labels.includes('Continue') && labels.includes('Revise node') && labels.includes('Stop run'), `gate buttons=${labels.join(',')}`);
      return `${labels.join(' / ')}`;
    });
    await recordKnown('S4', 'S4-03', 'Canvas notice while paused still says "Workflow run finished." (D-07)', async () => {
      const notice = await noticeText();
      if (notice === 'Workflow run finished.') throw new Error(`canvas notice while paused: "${notice}" (D-07)`);
      return `canvas notice: "${notice}"`;
    });

    // ---------------- S5 continue and read the result ----------------
    step('S5 continuing and reading the EISQCReport');
    await record('S5', 'S5-01', 'Continue completes the node', async () => {
      await page.locator('.decision-actions button', { hasText: 'Continue' }).click();
      await waitNodeStatus('EIS Basic Analysis', 'Completed');
      const status = await statusText();
      must(status.includes('Decision submitted: continue'), `status="${status}"`);
      return status;
    });
    await record('S5', 'S5-02', 'Preview shows the real EISQCReport values', async () => {
      const preview = (await page.locator('.preview-panel').innerText()).replace(/\n/g, ' ');
      must(/rows_valid"\s*:\s*13/.test(preview), `preview="${preview.slice(0, 160)}"`);
      must(/pass"\s*:\s*true/.test(preview), `preview="${preview.slice(0, 160)}"`);
      return 'rows_valid=13 pass=true';
    });
    await record('S5', 'S5-03', 'Latest output is available', async () => {
      must(await page.locator('.node-output').count() > 0, 'no Latest output section');
      return 'latest-output=present';
    });
    await record('S5', 'S5-04', 'Server holds the same result', async () => {
      const output = (await readState()).nodes.find((node) => node.type === 'eis_basic_qc')?.output;
      must(output?.rows_valid === 13 && output?.rows_retained === 13 && output?.pass === true, JSON.stringify(output));
      return `rows_valid=${output.rows_valid} rows_retained=${output.rows_retained}`;
    });

    // ---------------- S6 stop-run branch ----------------
    step('S6 stopping a branch and proving downstream did not run');
    await record('S6', 'S6-01', 'Normalize review gate saves as Graph v2', async () => {
      await nodeByLabel('Normalize / Column Mapping').locator('label.node-review-toggle input').check();
      await saveWorkflow();
      const normalize = (await readState()).nodes.find((node) => node.type === 'normalize_columns');
      must(normalize.review_policy?.after_run === true, 'normalize review policy not persisted');
      return `v${(await readState()).version}`;
    });
    await record('S6', 'S6-02', 'Run pauses at Normalize and leaves EIS unexecuted', async () => {
      await page.locator('button[aria-label="Run workflow from start"]').click();
      await waitNodeStatus('Normalize / Column Mapping', 'Waiting');
      const eis = await nodeStatus('EIS Basic Analysis');
      must(eis === 'Ready', `eis=${eis}`);
      const output = (await readState()).nodes.find((node) => node.type === 'eis_basic_qc')?.output;
      must(output === null || output === undefined, 'downstream output is not null');
      return `normalize=Waiting eis=${eis}`;
    });
    await record('S6', 'S6-03', 'Revise node opens an isolated proposal dialog and can be cancelled', async () => {
      await selectNode('Normalize / Column Mapping', 'normalize_columns-1');
      await page.locator('.decision-actions button', { hasText: 'Revise node' }).click();
      await page.locator('#revision-title').waitFor({ timeout: 10000 });
      const title = (await page.locator('#revision-title').innerText()).trim();
      await page.locator('.revision-dialog button', { hasText: 'Cancel' }).click();
      await page.locator('#revision-title').waitFor({ state: 'detached', timeout: 10000 });
      return `dialog="${title}"`;
    });
    await record('S6', 'S6-04', 'Stop run cancels the branch without executing downstream', async () => {
      await selectNode('Normalize / Column Mapping', 'normalize_columns-1');
      await page.locator('.decision-actions button', { hasText: 'Stop run' }).click();
      await page.waitForFunction(() => {
        const nodes = [...document.querySelectorAll('[data-testid="workflow-canvas"] article.workflow-node')];
        const normalize = nodes.find((node) => (node.getAttribute('aria-label') ?? '').startsWith('Normalize'));
        return (normalize?.querySelector('.node-status')?.textContent ?? '').trim() === 'Stopped';
      }, null, { timeout: 30000 });
      const state = await readState();
      const normalize = state.nodes.find((node) => node.type === 'normalize_columns');
      const eis = state.nodes.find((node) => node.type === 'eis_basic_qc');
      must(normalize.status === 'cancelled', `normalize=${normalize.status}`);
      must(eis.status !== 'completed', `eis=${eis.status}`);
      must(eis.output === null || eis.output === undefined, 'executed downstream has output');
      return `normalize=${normalize.status} eis=${eis.status} eisOutput=null`;
    });
    await record('S6', 'S6-05', 'Review can be switched off and saved', async () => {
      await nodeByLabel('Normalize / Column Mapping').locator('label.node-review-toggle input').uncheck();
      await saveWorkflow();
      const normalize = (await readState()).nodes.find((node) => node.type === 'normalize_columns');
      must(normalize.review_policy?.after_run === false, 'normalize review policy still on');
      return `v${(await readState()).version}`;
    });

    // ---------------- S7 export / import ----------------
    step('S7 exporting and re-importing the workflow');
    const exportPath = path.join(SHOTS, 'exported.matflow.json');
    await record('S7', 'S7-01', 'Export downloads a complete workflow document', async () => {
      const [download] = await Promise.all([
        page.waitForEvent('download', { timeout: 15000 }),
        page.locator('button[aria-label="Export workflow JSON"]').click(),
      ]);
      await download.saveAs(exportPath);
      const document = JSON.parse(fs.readFileSync(exportPath, 'utf8'));
      must(document.graph.nodes.length === 3 && document.graph.edges.length === 2, `nodes=${document.graph.nodes.length} edges=${document.graph.edges.length}`);
      const eis = document.graph.nodes.find((node) => node.type === 'eis_basic_qc');
      must(eis.review_policy?.after_run === true, 'exported review policy missing');
      return `${download.suggestedFilename()} (${document.graph.nodes.length}/${document.graph.edges.length})`;
    });
    await record('S7', 'S7-02', 'Deleting a node removes it from the draft', async () => {
      await canvas.locator('.react-flow__pane').click({ position: { x: 900, y: 520 } });
      await selectNode('Normalize / Column Mapping', 'normalize_columns-1');
      await page.locator('.danger-button').click();
      await page.waitForFunction(() => document.querySelectorAll('[data-testid="workflow-canvas"] article.workflow-node').length === 2, null, { timeout: 8000 });
      const notice = await noticeText();
      must(notice.includes('1 node removed from the draft.'), `notice="${notice}"`);
      return notice;
    });
    await record('S7', 'S7-03', 'Import restores the exported graph', async () => {
      await page.locator('input[aria-label="Import workflow JSON file"]').setInputFiles(exportPath);
      await waitNotice(/Imported /);
      must((await nodeCount()) === 3, `nodes=${await nodeCount()}`);
      must((await edgeCount()) === 2, `edges=${await edgeCount()}`);
      return await noticeText();
    });
    await record('S7', 'S7-04', 'Saving after import produces a clear outcome', async () => {
      await page.locator('button[aria-label="Save workflow"]').click();
      await waitNotice(/Saved as graph|already saved/);
      const notice = await noticeText();
      must(/already saved/.test(notice) || /Saved as graph/.test(notice), `notice="${notice}"`);
      return notice;
    });

    // ---------------- S8 QE replay ----------------
    step('S8 replaying the pinned QE archive');
    await record('S8', 'S8-01', 'QE demo is disabled while the workspace is not empty', async () => {
      const qe = page.locator('.topbar-actions button', { hasText: 'Run MgO QE replay demo' });
      must(await qe.isDisabled(), 'QE demo button is enabled on a non-empty workspace');
      must((await qe.getAttribute('title') ?? '').includes('empty workspace'), 'disabled QE button does not explain why');
      return `title="${await qe.getAttribute('title')}"`;
    });
    await record('S8', 'S8-02', 'Clear workflow plus Save empties the server graph', async () => {
      await canvas.locator('.react-flow__pane').click({ position: { x: 900, y: 520 } });
      await page.locator('.inspector-empty button', { hasText: 'Clear workflow' }).click();
      await page.waitForFunction(() => document.querySelectorAll('[data-testid="workflow-canvas"] article.workflow-node').length === 0, null, { timeout: 8000 });
      await saveWorkflow();
      const state = await readState();
      must(state.nodes.length === 0 && state.edges.length === 0, `nodes=${state.nodes.length} edges=${state.edges.length}`);
      return `v${state.version} 0/0`;
    });
    await record('S8', 'S8-03', 'QE replay completes with the archived energy', async () => {
      await page.locator('.topbar-actions button', { hasText: 'Run MgO QE replay demo' }).click();
      await waitStatus('MgO QE replay complete', 180000);
      const status = await statusText();
      must(status.includes('-2417.17683284 Ry'), `status="${status}"`);
      must(status.includes('no Slurm job submitted'), `status="${status}"`);
      return status;
    });
    await record('S8', 'S8-04', 'Four QE nodes complete', async () => {
      await page.waitForFunction(() => {
        const nodes = [...document.querySelectorAll('[data-testid="workflow-canvas"] article.workflow-node')];
        return nodes.length === 4 && nodes.every((node) => (node.querySelector('.node-status')?.textContent ?? '').trim() === 'Completed');
      }, null, { timeout: 90000 });
      const entries = await nodeStatuses();
      must(entries.length === 4 && entries.every((entry) => entry.status === 'Completed'), JSON.stringify(entries));
      return entries.map((entry) => `=${entry.status}`).join(' / ');
    });
    await record('S8', 'S8-05', 'QE preview shows the replay provenance and parsed values', async () => {
      await selectNode('Parse QE result', 'qe-demo-result');
      await page.locator('.qe-result-preview').waitFor({ timeout: 10000 });
      const preview = (await page.locator('.qe-result-preview').innerText()).replace(/\n/g, ' | ');
      must(preview.includes('Historical output replay · Slurm not submitted'), `preview="${preview}"`);
      must(preview.includes('-2417.17683284'), `preview="${preview}"`);
      must(preview.includes('9.7133'), `preview="${preview}"`);
      return preview;
    });
    await record('S8', 'S8-06', 'Server holds the four-node QE graph', async () => {
      const state = await readState();
      must(state.nodes.length === 4 && state.edges.length === 3, `nodes=${state.nodes.length} edges=${state.edges.length}`);
      return `v${state.version} 4/3`;
    });

    // ---------------- S9 Chinese routing ----------------
    step('S9 routing a Chinese research question');
    await record('S9', 'S9-01', 'Route dialog exposes the question field and 14 input types', async () => {
      await page.locator('.topbar-actions button', { hasText: 'Route a research task' }).click();
      await page.locator('.task-dialog').waitFor();
      must((await page.locator('textarea[aria-label="Research question"]').count()) === 1, 'no research question field');
      const types = await page.locator('.type-option').count();
      must(types === 14, `input types=${types}`);
      return `types=${types}`;
    });
    const routedAt = Date.now();
    await record('S9', 'S9-02', 'A Chinese prompt gets a routing decision', async () => {
      await page.locator('textarea[aria-label="Research question"]').fill(ROUTE_PROMPT);
      await page.locator('.type-option', { hasText: 'TypedTable' }).locator('input').check();
      await page.locator('.task-dialog button[type=submit]').click();
      await page.locator('.decision-dialog .audit-facts').waitFor({ timeout: 120000 });
      const status = await statusText();
      must(/Routing decision saved|waiting for human confirmation/.test(status), `status="${status}"`);
      return `status="${status}" after ${((Date.now() - routedAt) / 1000).toFixed(2)} s`;
    });
    await record('S9', 'S9-03', 'Decision record exposes provenance, model and confidence', async () => {
      const facts = (await page.locator('.decision-dialog .audit-facts').innerText()).replace(/\n/g, ' | ');
      must(/Decision source\s*\|\s*llm/.test(facts), `facts="${facts}"`);
      must(/Model\s*\|\s*[a-z0-9.-]+/.test(facts), `facts="${facts}"`);
      must(/Confidence\s*\|\s*\d+%/.test(facts), `facts="${facts}"`);
      return facts;
    });
    await record('S9', 'S9-04', 'The decision selects eis_basic_qc with a sanitized rationale', async () => {
      const selected = (await page.locator('.decision-dialog .tool-list').innerText()).replace(/\n/g, ' | ');
      must(selected.includes('eis_basic_qc'), `selected="${selected}"`);
      const rationale = (await page.locator('.decision-dialog .rationale p').innerText()).trim();
      must(rationale.includes('Jev routing unavailable; the LLM decided instead.'), `rationale="${rationale}"`);
      must(!/urlopen|WinError|Connection refused|10061/i.test(rationale), `rationale leaks the transport error: "${rationale}"`);
      return `${selected} :: ${rationale.slice(0, 120)}`;
    });
    await record('S9', 'S9-05', 'Candidate retrieval and the user prompt are shown', async () => {
      const candidates = await page.locator('.decision-dialog .candidate-list li').count();
      must(candidates > 0, 'no candidate tools listed');
      const prompt = (await page.locator('.decision-dialog .prompt-evidence p').innerText()).trim();
      must(prompt === ROUTE_PROMPT, `prompt="${prompt}"`);
      await page.locator('.dialog-close').click();
      return `candidates=${candidates}`;
    });
    await record('S9', 'S9-06', 'The Decision record button reopens the recorded decision', async () => {
      await page.locator('.topbar-actions button', { hasText: 'Decision record' }).click();
      await page.locator('.decision-dialog .audit-facts').waitFor({ timeout: 10000 });
      const facts = (await page.locator('.decision-dialog .audit-facts').innerText()).replace(/\n/g, ' | ');
      await page.locator('.dialog-close').click();
      return facts;
    });
    await recordKnown('S9', 'S9-07', 'QE demo reuses the routed question and rejects it when it names no MgO/SCF (documented trap)', async () => {
      await canvas.locator('.react-flow__pane').click({ position: { x: 900, y: 520 } });
      await page.locator('.inspector-empty button', { hasText: 'Clear workflow' }).click();
      await page.waitForFunction(() => document.querySelectorAll('[data-testid="workflow-canvas"] article.workflow-node').length === 0, null, { timeout: 8000 });
      await saveWorkflow();
      await page.locator('.topbar-actions button', { hasText: 'Run MgO QE replay demo' }).click();
      try {
        await waitStatus('MgO QE replay complete', 20000);
        return 'QE replay started with the routed question';
      } catch {
        throw new Error(`QE demo rejected the routed question: "${await statusText()}"`);
      }
    });

    // ---------------- S10 wrap-up ----------------
    step('S10 checking narrow viewport and API docs');
    await record('S10', 'S10-01', '1280x720 has no horizontal overflow and keeps the actions visible', async () => {
      await page.setViewportSize({ width: 1280, height: 720 });
      await page.waitForTimeout(600);
      const metrics = await page.evaluate(() => ({
        innerWidth: window.innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        canvas: Math.round(document.querySelector('[data-testid="workflow-canvas"]')?.getBoundingClientRect().width ?? 0),
        actions: [...document.querySelectorAll('.topbar-actions button')].filter((button) => button.getBoundingClientRect().width > 0).length,
      }));
      must(metrics.scrollWidth === metrics.innerWidth, `scrollWidth=${metrics.scrollWidth} innerWidth=${metrics.innerWidth}`);
      must(metrics.canvas > 0, 'canvas has no width');
      must(metrics.actions === 3, `visible topbar actions=${metrics.actions}`);
      await page.setViewportSize({ width: viewWidth, height: viewHeight });
      return JSON.stringify(metrics);
    });
    await record('S10', 'S10-02', 'Registry still lists 18 tools', async () => {
      await page.locator('#workspace-tab').click();
      const count = await page.locator('.registry-list .registry-item').count();
      must(count === 18, `registry rows=${count}`);
      return `registry=${count}`;
    });
    await record('S10', 'S10-03', 'API docs answer over HTTP', async () => {
      const response = await page.request.get(DOCS_URL);
      must(response.ok(), `${DOCS_URL} -> ${response.status()}`);
      return `${DOCS_URL} -> ${response.status()}`;
    });

    // ---------------- global checks ----------------
    await record('G', 'G-01', 'No uncaught page errors', async () => {
      must(pageErrors.length === 0, `page errors=${pageErrors.join(' | ')}`);
      return 'pageerrors=0';
    });
    await record('G', 'G-02', 'No unexpected console errors', async () => {
      const unexpected = consoleErrors.filter((text) => !/422|Failed to load resource/.test(text));
      must(unexpected.length === 0, `console errors=${unexpected.join(' | ')}`);
      return `console=${consoleErrors.length} (expected: the routed-question QE rejection)`;
    });
  } catch (error) {
    checks.push({ scene: 'RUN', id: 'RUN-ABORT', name: 'first failing check aborted the walkthrough', status: 'FAIL', detail: detailOf(error.message) });
    const file = await failureShot('failure');
    console.error(`\naborted at a failing check (screenshot ${file}):`, error.message);
  } finally {
    const summary = checks.reduce((accumulator, check) => {
      accumulator[check.status] = (accumulator[check.status] ?? 0) + 1;
      return accumulator;
    }, {});
    const evidence = {
      checkedAt: STARTED_AT,
      finishedAt: new Date().toISOString(),
      webUrl: WEB_URL,
      api: API,
      viewport: `${viewWidth}x${viewHeight}`,
      sceneOrder: ['S0', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'G'],
      summary,
      checks,
      steps: log,
      pageErrors,
      consoleErrors,
    };
    fs.writeFileSync(EVIDENCE, JSON.stringify(evidence, null, 2));
    await browser.close();
    console.log(`\nsummary: ${JSON.stringify(summary)}`);
    console.log(`evidence: ${EVIDENCE}`);
    if ((summary.FAIL ?? 0) > 0) process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(`\n${error.message}`);
  process.exitCode = error.exitCode ?? 1;
});
