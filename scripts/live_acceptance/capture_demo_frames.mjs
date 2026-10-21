#!/usr/bin/env node
// Capture the exact browser frames a MatFlow demo video shows, at the recording viewport.
//
// It drives the real WebUI (no mocks, no HTTP shortcuts for in-page actions) and
// writes one PNG per storyboard scene plus a JSON evidence file with the values the
// narration quotes. Use it to refresh docs/acceptance/2026-10-20-live/demo-tutorial/
// screenshots after a UI change, or to check that a demo machine shows what the
// tutorial claims.
//
// Preconditions: backend + WebUI already running, workspace empty (a fresh save).
// See docs/acceptance/2026-10-20-live/DEMO_TUTORIAL.zhcn.md for the full procedure.
//
// Environment:
//   MATFLOW_WEB_URL        WebUI URL              (default http://127.0.0.1:5173/)
//   MATFLOW_API            API base, with /api   (default http://127.0.0.1:8000/api)
//   MATFLOW_FRONTEND_REPO  frontend checkout with playwright installed (default ../matflow-frontend)
//   MATFLOW_DEMO_CSV       dataset to import     (default examples/data/01_eis_basic_qc/eis_spectrum.csv)
//   MATFLOW_FRAME_OUT      screenshot directory  (default docs/acceptance/2026-10-20-live/demo-tutorial/screenshots)
//   MATFLOW_FRAME_EVIDENCE evidence JSON path    (default <parent of frame out>/capture.json)
//   MATFLOW_ROUTE_PROMPT   Chinese routing prompt for the decision-record scene
//   MATFLOW_VIEWPORT       WxH                   (default 1920x1080)
//
// Exit codes: 0 = all frames captured, 2 = precondition failed, 1 = capture failed.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '..', '..');

const WEB_URL = process.env.MATFLOW_WEB_URL ?? 'http://127.0.0.1:5173/';
const API = (process.env.MATFLOW_API ?? 'http://127.0.0.1:8000/api').replace(/\/$/, '');
const FRONTEND = path.resolve(process.env.MATFLOW_FRONTEND_REPO ?? path.join(repo, '..', 'matflow-frontend'));
const CSV = path.resolve(process.env.MATFLOW_DEMO_CSV ?? path.join(repo, 'examples', 'data', '01_eis_basic_qc', 'eis_spectrum.csv'));
const OUT = path.resolve(process.env.MATFLOW_FRAME_OUT ?? path.join(repo, 'docs', 'acceptance', '2026-10-20-live', 'demo-tutorial', 'screenshots'));
const EVIDENCE = path.resolve(process.env.MATFLOW_FRAME_EVIDENCE ?? path.join(path.dirname(OUT), 'capture.json'));
const DATASET_REF = (() => { const relative = path.relative(repo, CSV); return relative.startsWith('..') ? path.basename(CSV) : relative.split(path.sep).join('/'); })();
const ROUTE_PROMPT = process.env.MATFLOW_ROUTE_PROMPT
  ?? '请对这份电化学阻抗谱数据做基本质控：检查高频段虚部符号是否为负、低频段是否发散，并给出质控结论。';
const [viewWidth, viewHeight] = (process.env.MATFLOW_VIEWPORT ?? '1920x1080').split('x').map(Number);

const log = [];
const step = (message) => { log.push({ at: new Date().toISOString(), message }); console.log('·', message); };

function fail(message, code = 1) {
  const error = new Error(message);
  error.exitCode = code;
  throw error;
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
  if (!fs.existsSync(path.join(repo, '.venv'))) console.warn('note: no backend virtualenv was found; assuming the backend is started elsewhere');

  const { chromium } = await loadPlaywright();
  fs.mkdirSync(OUT, { recursive: true });
  fs.mkdirSync(path.dirname(EVIDENCE), { recursive: true });

  const browser = await chromium.launch();
  const consoleErrors = [];
  const pageErrors = [];
  const evidence = {
    capturedAt: new Date().toISOString(),
    webUrl: WEB_URL,
    api: API,
    viewport: `${viewWidth}x${viewHeight}`,
    dataset: DATASET_REF,
    routePrompt: ROUTE_PROMPT,
    steps: log,
    states: {},
    results: {},
    consoleErrors,
    pageErrors,
  };

  try {
    const page = await browser.newPage({ viewport: { width: viewWidth, height: viewHeight }, acceptDownloads: true, deviceScaleFactor: 1 });
    page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
    page.on('pageerror', (error) => pageErrors.push(String(error)));

    const api = async (endpoint) => {
      const response = await page.request.get(`${API}${endpoint}`);
      if (!response.ok()) fail(`${API}${endpoint} answered ${response.status()}; is MATFLOW_API right?`, 2);
      return response.json();
    };
    const canvas = page.locator('[data-testid="workflow-canvas"]');
    const nodeByLabel = (label) => canvas.locator('article.workflow-node').filter({ hasText: label }).first();
    const shot = async (name) => { await page.screenshot({ path: path.join(OUT, name) }); step(`screenshot ${name}`); };
    const statusText = async () => (await page.locator('.connection').innerText()).trim();
    const waitStatus = async (fragment, timeout = 90000) => {
      await page.waitForFunction((text) => (document.querySelector('.connection')?.textContent ?? '').includes(text), fragment, { timeout });
    };
    const waitNodeStatus = async (label, wanted, timeout = 90000) => {
      await page.waitForFunction(({ nodeLabel, nodeStatus }) => {
        const nodes = [...document.querySelectorAll('[data-testid="workflow-canvas"] article.workflow-node')];
        const node = nodes.find((candidate) => (candidate.getAttribute('aria-label') ?? '').startsWith(nodeLabel));
        return (node?.querySelector('.node-status')?.textContent ?? '').trim() === nodeStatus;
      }, { nodeLabel: label, nodeStatus: wanted }, { timeout });
    };
    const edgeCount = async () => canvas.locator('.react-flow__edge').count();
    const clickPort = async (label, portId) => {
      await nodeByLabel(label).locator(`.workflow-port[data-port-id="${portId}"]`).first().locator('.react-flow__handle').click({ force: true });
      step(`clicked the ${portId} port on ${label}`);
    };
    const openConnectMode = async (label, portId) => {
      for (let attempt = 1; attempt <= 3; attempt += 1) {
        await clickPort(label, portId);
        try {
          await page.locator('.connect-helper').waitFor({ timeout: 2000 });
          return;
        } catch {
          step(`connect mode did not open from ${label}.${portId} (attempt ${attempt}); clicking again`);
          await page.keyboard.press('Escape');
          await page.waitForTimeout(250);
        }
      }
      throw new Error(`could not start a connection from ${label}.${portId} through the UI`);
    };
    const connectPorts = async (sourceLabel, sourcePort, targetLabel, targetPort) => {
      for (let attempt = 1; attempt <= 3; attempt += 1) {
        const count = await edgeCount();
        await openConnectMode(sourceLabel, sourcePort);
        await clickPort(targetLabel, targetPort);
        try {
          await page.waitForFunction((expected) => document.querySelectorAll('[data-testid="workflow-canvas"] .react-flow__edge').length === expected, count + 1, { timeout: 5000 });
          step(`connected ${sourcePort} -> ${targetPort} on attempt ${attempt}`);
          return;
        } catch {
          step(`connect ${sourcePort} -> ${targetPort} did not register on attempt ${attempt}; retrying`);
          await page.keyboard.press('Escape');
          await page.waitForTimeout(300);
        }
      }
      throw new Error(`could not connect ${sourcePort} -> ${targetPort} through the UI`);
    };
    const addTool = async (label) => {
      await page.locator('#library-tab').click();
      await page.locator('button.tool-card').filter({ hasText: label }).first().click();
      await page.waitForFunction((text) => [...document.querySelectorAll('article.workflow-node strong')].some((element) => element.textContent.trim() === text), label);
      step(`added node ${label}`);
    };
    const selectNode = async (label, expectedId) => {
      await nodeByLabel(label).click();
      await page.waitForFunction((id) => (document.querySelector('.node-inspector .panel-title code')?.textContent ?? '').includes(id), expectedId, { timeout: 8000 });
      step(`selected ${expectedId}`);
    };
    const setParam = async (label, value) => {
      const field = page.locator('.inspector-params label.inspector-field').filter({ has: page.locator('span', { hasText: label }) }).first();
      await field.locator('input').fill(String(value));
      await field.locator('input').blur();
      step(`set ${label}=${value}`);
    };
    const saveWorkflow = async () => {
      await page.locator('button[aria-label="Save workflow"]').click();
      await page.waitForFunction(() => /Saved as graph|already saved/i.test(document.querySelector('.editor-notice')?.textContent ?? ''), null, { timeout: 30000 });
      step(`saved: ${(await page.locator('.editor-notice').innerText()).trim()}`);
    };

    // Precondition: the WebUI answers and the workspace is empty (a fresh save).
    await page.goto(WEB_URL, { waitUntil: 'domcontentloaded' });
    await page.locator('.workflow-editor').waitFor({ timeout: 30000 });
    await waitStatus('Connected');
    const before = await api('/state');
    if (before.state.nodes.length || before.state.edges.length) {
      fail(`the workspace is not empty (v${before.state.version}, ${before.state.nodes.length} nodes / ${before.state.edges.length} edges).\nUse a fresh save, e.g. $env:MATFLOW_SAVE = 'demo-video' before starting the launcher.`, 2);
    }
    const uploads = await api('/uploads');
    if ((uploads.files ?? []).length) {
      fail(`the workspace already lists ${uploads.files.length} imported dataset(s); the first frame expects none.\nUse a fresh save, e.g. $env:MATFLOW_SAVE = 'demo-video' before starting the launcher.`, 2);
    }
    evidence.results.initialStatus = await statusText();
    evidence.results.layout = await page.evaluate(() => ({
      canvas: Math.round(document.querySelector('[data-testid="workflow-canvas"]')?.getBoundingClientRect().width ?? 0),
      inspector: Math.round(document.querySelector('.node-inspector')?.getBoundingClientRect().width ?? 0),
    }));

    // Scene 1: empty workbench.
    await shot('00-empty-workspace.png');

    // Scene 2: import a dataset.
    await page.locator('label.dataset-upload input[type=file]').setInputFiles(CSV);
    await page.locator('.dataset-detail').waitFor({ timeout: 30000 });
    evidence.results.datasetDetail = (await page.locator('.dataset-detail').innerText()).replace(/\n/g, ' | ');
    await shot('01-import-dataset.png');

    // Scene 3: build the typed graph.
    await addTool('Raw File Import');
    await page.locator('.inspector-params select').first().selectOption({ index: 1 });
    evidence.results.datasetUploadId = await page.locator('.inspector-params select').first().inputValue();
    await addTool('Normalize / Column Mapping');
    await addTool('EIS Basic Analysis');
    await connectPorts('Raw File Import', 'raw', 'Normalize / Column Mapping', 'raw');
    await connectPorts('Normalize / Column Mapping', 'table', 'EIS Basic Analysis', 'data');
    evidence.results.edges = await edgeCount();
    await shot('02-graph-built.png');

    // Scene 4: edit the column mapping in the Inspector.
    await selectNode('EIS Basic Analysis', 'eis_basic_qc-1');
    await setParam('frequency column', 'frequency_hz');
    await setParam('real column', 'z_real_ohm');
    await setParam('imag column', 'z_imag_ohm');
    await shot('03-inspector-params.png');

    // Scene 5: turn on the review gate and save a version.
    await nodeByLabel('EIS Basic Analysis').locator('label.node-review-toggle input').check();
    step('review gate on the EIS node');
    await saveWorkflow();
    evidence.states.afterSave = (await api('/state')).state;
    await shot('04-saved-review-on.png');

    // Scene 6: run to the human review gate.
    await page.locator('button[aria-label="Run workflow from start"]').click();
    await waitNodeStatus('EIS Basic Analysis', 'Waiting');
    await selectNode('EIS Basic Analysis', 'eis_basic_qc-1');
    await page.locator('.decision-actions').waitFor({ timeout: 10000 });
    evidence.results.pausedStatus = await statusText();
    evidence.results.reviewPrompt = (await page.locator('.decision-actions h3').innerText()).trim();
    evidence.states.waiting = (await api('/state')).state;
    await shot('05-review-waiting.png');

    // Scene 7: continue and read the real result.
    await page.locator('.decision-actions button', { hasText: 'Continue' }).click();
    await waitNodeStatus('EIS Basic Analysis', 'Completed');
    evidence.results.completedStatus = await statusText();
    evidence.states.completed = (await api('/state')).state;
    evidence.results.eisOutput = evidence.states.completed.nodes.find((node) => node.type === 'eis_basic_qc')?.output ?? null;
    await shot('06-completed-result.png');

    // Scene 8: clear the workspace, then replay the pinned QE archive.
    // The QE demo must run before the routed task: the route dialog writes a non-MgO
    // question into state, and the QE demo reuses that text (HTTP 422) when it names no MgO/SCF.
    await canvas.locator('.react-flow__pane').click({ position: { x: 900, y: 520 } });
    await page.locator('.inspector-empty button', { hasText: 'Clear workflow' }).click();
    await page.waitForFunction(() => document.querySelectorAll('[data-testid="workflow-canvas"] article.workflow-node').length === 0);
    await saveWorkflow();
    evidence.states.cleared = (await api('/state')).state;
    await shot('07-cleared-workspace.png');

    await page.locator('.topbar-actions button', { hasText: 'Run MgO QE replay demo' }).click();
    await waitStatus('MgO QE replay complete', 180000);
    await page.waitForFunction(() => document.querySelectorAll('[data-testid="workflow-canvas"] article.workflow-node').length >= 4);
    evidence.results.qeStatus = await statusText();
    evidence.states.qe = (await api('/state')).state;
    await shot('08-qe-replay.png');

    // Scene 9: route a Chinese research question and open the audit record.
    await page.locator('.topbar-actions button', { hasText: 'Route a research task' }).click();
    await page.locator('.task-dialog').waitFor();
    await page.locator('textarea[aria-label="Research question"]').fill(ROUTE_PROMPT);
    await shot('09-route-dialog.png');
    await page.locator('.type-option', { hasText: 'TypedTable' }).locator('input').check();
    const routedAt = Date.now();
    await page.locator('.task-dialog button[type=submit]').click();
    await page.locator('.decision-dialog .audit-facts').waitFor({ timeout: 120000 });
    evidence.results.routingSeconds = (Date.now() - routedAt) / 1000;
    evidence.results.decisionFacts = (await page.locator('.decision-dialog .audit-facts').innerText()).replace(/\n/g, ' | ');
    evidence.results.decisionBadge = (await page.locator('.decision-dialog .state-badge').innerText()).trim();
    evidence.results.selectedTools = (await page.locator('.decision-dialog .tool-list').innerText().catch(() => '')).replace(/\n/g, ' | ');
    await shot('10-decision-record.png');
    await page.locator('.dialog-close').click();

    evidence.results.finalStatus = await statusText();
    fs.writeFileSync(EVIDENCE, JSON.stringify(evidence, null, 2));
    console.log(`\nframes:    ${OUT}`);
    console.log(`evidence:  ${EVIDENCE}`);
    console.log(`routing:   ${evidence.results.routingSeconds.toFixed(2)} s`);
    console.log(`QE:        ${evidence.results.qeStatus}`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(`\n${error.message}`);
  process.exitCode = error.exitCode ?? 1;
});
