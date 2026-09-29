import { expect, test } from '@playwright/test';
import { createRequire } from 'node:module';
import { writeFile } from 'node:fs/promises';

const require = createRequire(import.meta.url);

async function audit(page, testInfo, name) {
  await page.addScriptTag({ path: require.resolve('axe-core') });
  const result = await page.evaluate(async () => {
    const report = await window.axe.run(document, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'] },
    });
    return { violations: report.violations, incomplete: report.incomplete.length, passes: report.passes.length };
  });
  await writeFile(testInfo.outputPath(`${name}-axe.json`), JSON.stringify(result, null, 2));
  expect(result.violations).toEqual([]);
}

async function addTool(page, name) {
  await page.getByRole('tab', { name: 'Tool library' }).click();
  await page.locator('.tool-card').filter({ hasText: name }).click();
}

async function connectPorts(page, sourceNodeName, sourcePort, targetNodeName, targetPort) {
  const source = page.getByLabel(`${sourceNodeName} workflow node`).locator(`[aria-label="output ${sourcePort}"]`);
  const target = page.getByLabel(`${targetNodeName} workflow node`).locator(`[aria-label="input ${targetPort}"]`);
  await source.scrollIntoViewIfNeeded();
  await target.scrollIntoViewIfNeeded();
  const sourceBox = await source.boundingBox();
  const targetBox = await target.boundingBox();
  expect(sourceBox).toBeTruthy();
  expect(targetBox).toBeTruthy();
  await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(targetBox.x + targetBox.width / 2, targetBox.y + targetBox.height / 2, { steps: 8 });
  await page.mouse.up();
}

test.beforeEach(async ({ request }) => {
  const response = await request.post('http://127.0.0.1:8001/api/reset?include_settings=true');
  expect(response.ok()).toBeTruthy();
});

test.afterEach(async ({ request }) => {
  await request.post('http://127.0.0.1:8001/api/reset?include_settings=true');
});

test('renders a server graph with a separate connection point for every typed port', async ({ page, request }) => {
  const patch = await request.post('http://127.0.0.1:8001/api/patch', {
    data: {
      base_version: 0,
      rationale: 'Browser rendering fixture',
      operations: [
        { op: 'add_node', node: { id: 'import', type: 'raw_file_import', position: { x: 40, y: 120 } } },
        { op: 'add_node', node: { id: 'normalize', type: 'normalize_columns', position: { x: 390, y: 120 } } },
        { op: 'add_node', node: { id: 'qc', type: 'eis_basic_qc', position: { x: 740, y: 70 } } },
        { op: 'add_node', node: { id: 'plot', type: 'plot_nyquist', position: { x: 1090, y: 20 } } },
        { op: 'connect', edge: { id: 'raw-table', source: 'import', source_port: 'raw', target: 'normalize', target_port: 'raw' } },
        { op: 'connect', edge: { id: 'table-qc', source: 'normalize', source_port: 'table', target: 'qc', target_port: 'data' } },
        { op: 'connect', edge: { id: 'data-plot', source: 'qc', source_port: 'data', target: 'plot', target_port: 'data' } },
      ],
    },
  });
  expect(patch.ok()).toBeTruthy();

  await page.goto('/');
  const canvas = page.getByTestId('workflow-canvas');
  await expect(canvas).toBeVisible();
  await expect(canvas.getByLabel('EIS Basic Analysis workflow node')).toBeVisible();
  await expect(canvas.locator('[data-port-id="report"]')).toBeVisible();
  await expect(canvas.locator('[data-port-id="data"]')).toHaveCount(3);
  await expect(canvas.locator('.react-flow__edge')).toHaveCount(3);
  await expect(page.getByText('4 nodes · 3 edges', { exact: true })).toBeVisible();
  const edgePath = canvas.locator('.react-flow__edge-path').first();
  await expect(edgePath).toHaveAttribute('d', /C/);
  await expect(edgePath).toHaveAttribute('marker-end', /arrowclosed/);
  const geometry = await canvas.evaluate(() => {
    const node = document.querySelector('[aria-label="Normalize / Column Mapping workflow node"]');
    const input = node.querySelector('[aria-label^="input raw"]');
    const output = node.querySelector('[aria-label^="output table"]');
    const nodeBox = node.getBoundingClientRect();
    const inputBox = input.getBoundingClientRect();
    const outputBox = output.getBoundingClientRect();
    return { nodeBox: { left: nodeBox.left, right: nodeBox.right }, inputCenter: inputBox.left + inputBox.width / 2, outputCenter: outputBox.left + outputBox.width / 2, inputCssSize: Number.parseFloat(getComputedStyle(input).width), outputCssSize: Number.parseFloat(getComputedStyle(output).width) };
  });
  expect(geometry.inputCssSize).toBe(16);
  expect(geometry.outputCssSize).toBe(16);
  expect(Math.abs(geometry.inputCenter - geometry.nodeBox.left)).toBeLessThanOrEqual(1);
  expect(Math.abs(geometry.outputCenter - geometry.nodeBox.right)).toBeLessThanOrEqual(1);
});

test('researcher can build, save, export, and run a workflow from the editor', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Import dataset').setInputFiles({
    name: 'sample-eis.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('frequency_hz,z_real,z_imag\n1000,5,-1\n100,8,-3\n10,12,-5\n'),
  });
  await expect(page.getByLabel('Imported datasets').getByText('sample-eis.csv', { exact: true })).toBeVisible();

  await addTool(page, 'Raw File Import');
  await page.getByLabel('Node inspector').getByLabel('Dataset').selectOption({ label: 'sample-eis.csv' });
  await addTool(page, 'Normalize / Column Mapping');
  await addTool(page, 'EIS Basic Analysis');

  await page.getByLabel('Raw File Import workflow node').locator('[aria-label="output raw, RawData"]').click();
  await expect(page.getByText(/Choose a highlighted input port/)).toBeVisible();
  await page.getByLabel('Normalize / Column Mapping workflow node').locator('[aria-label="input raw, RawData"]').click();
  await connectPorts(page, 'Normalize / Column Mapping', 'table, TypedTable', 'EIS Basic Analysis', 'data, TypedTable');
  await expect(page.locator('.react-flow__edge')).toHaveCount(2);
  await page.getByLabel('Raw File Import workflow node').getByRole('checkbox').check();

  await page.getByRole('button', { name: 'Save workflow' }).click();
  await expect(page.getByText('Saved · Graph v1', { exact: true })).toBeVisible();

  await page.getByLabel('Raw File Import workflow node').click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Rename node' }).click();
  await page.getByLabel('Node name').fill('Source data');
  await page.getByRole('button', { name: 'Rename node', exact: true }).click();
  await expect(page.getByLabel('Source data workflow node')).toBeVisible();

  await page.getByLabel('Source data workflow node').click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Modify with AI' }).click();
  await page.getByLabel('What should change?').fill('Clarify the input node and keep its ports compatible.');
  await page.getByRole('button', { name: 'Generate proposal' }).click();
  await expect(page.getByRole('heading', { name: 'Connection migration' })).toBeVisible();
  await page.getByRole('button', { name: 'Apply revision' }).click();
  await expect(page.getByLabel('AI revised input workflow node')).toBeVisible();
  await expect(page.locator('.react-flow__edge')).toHaveCount(2);

  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export workflow JSON' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain('.matflow.json');

  await page.getByRole('button', { name: 'Run workflow from start' }).click();
  await expect(page.getByLabel('AI revised input workflow node')).toContainText('Waiting');
  await page.getByLabel('AI revised input workflow node').click();
  await expect(page.locator('.preview-table')).toBeVisible();
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await expect(page.getByLabel('EIS Basic Analysis workflow node')).toContainText('Completed');
});

test('researcher can import a portable workflow JSON file and save it', async ({ page }) => {
  await page.goto('/');
  await page.locator('input[type="file"][accept*="application/json"]').setInputFiles({
    name: 'portable.matflow.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify({
      format: 'matflow.workflow',
      format_version: '1.0',
      graph: {
        graph_id: 'portable-demo',
        nodes: [{ id: 'input-1', type: 'raw_file_import', label: 'Portable input', params: {}, position: { x: 120, y: 100 } }],
        edges: [],
      },
    })),
  });
  await expect(page.getByLabel('Portable input workflow node')).toBeVisible();
  await expect(page.getByText(/Imported portable\.matflow\.json/)).toBeVisible();
  await page.getByRole('button', { name: 'Save workflow' }).click();
  await expect(page.getByText('Saved · Graph v1', { exact: true })).toBeVisible();
});

test('researcher can route an EIS task and inspect its auditable decision', async ({ page }, testInfo) => {
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Research workbench' })).toBeVisible();
  await page.keyboard.press('Tab');
  await expect(page.getByText('Skip to main content', { exact: true })).toBeFocused();
  await page.keyboard.press('Tab');
  expect((await page.locator('.skip-link').boundingBox())?.y).toBeLessThan(0);
  await expect(page.getByRole('tabpanel', { name: 'Workspace' }).getByText('eis_basic_qc', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Route a research task' }).click();
  await page.getByLabel('Research question').fill('Run basic EIS quality checks');
  await page.getByRole('checkbox', { name: 'TypedTable' }).check();
  await page.getByRole('button', { name: 'Get routing decision' }).click();

  await expect(page.getByRole('heading', { name: 'Decision record' })).toBeVisible();
  await expect(page.getByRole('dialog').locator('code').filter({ hasText: 'eis_basic_qc' }).first()).toBeVisible();
  await expect(page.locator('.prompt-evidence').getByText('Run basic EIS quality checks', { exact: true })).toBeVisible();
  await audit(page, testInfo, 'workbench-desktop');
  await page.screenshot({ path: testInfo.outputPath('workbench-desktop.png'), fullPage: true });
});

test('research workbench remains usable on a narrow screen', async ({ browser }, testInfo) => {
  const context = await browser.newContext({ viewport: { width: 375, height: 812 } });
  const page = await context.newPage();
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Research workbench' })).toBeVisible();
  await page.getByRole('button', { name: 'Route a research task' }).click();
  await expect(page.getByLabel('Research question')).toBeVisible();
  await page.getByRole('button', { name: 'Close route task dialog' }).click();
  await page.getByRole('button', { name: 'Open workspace sidebar' }).click();
  await expect(page.getByRole('tab', { name: 'Tool library' })).toBeVisible();
  await audit(page, testInfo, 'workbench-mobile');
  await page.screenshot({ path: testInfo.outputPath('workbench-mobile.png'), fullPage: true });
  await context.close();
});

test('keyboard users meet the visible-focus and touch-target baseline', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Research workbench' })).toBeVisible();
  await page.getByRole('tab', { name: 'Tool library' }).click();
  await page.evaluate(() => document.activeElement?.blur());
  const controls = [
    page.locator('.canvas-action-group button').first(),
    page.getByPlaceholder('Search tools'),
    page.locator('.tool-card').first(),
    page.getByRole('button', { name: 'Route a research task' }),
  ];

  for (const locator of controls) {
    await locator.focus();
    const metrics = await locator.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      return { width: rect.width, height: rect.height, outline: getComputedStyle(element).outlineWidth };
    });
    expect(metrics.width).toBeGreaterThanOrEqual(44);
    expect(metrics.height).toBeGreaterThanOrEqual(44);
    expect(metrics.outline).not.toBe('0px');
  }
});
