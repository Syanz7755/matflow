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

test.beforeEach(async ({ request }) => {
  const response = await request.post('http://127.0.0.1:8001/api/reset');
  expect(response.ok()).toBeTruthy();
});

test('researcher can route an EIS task and inspect its auditable decision', async ({ page }, testInfo) => {
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Research workbench' })).toBeVisible();
  await page.keyboard.press('Tab');
  await expect(page.getByText('Skip to main content', { exact: true })).toBeFocused();
  await page.keyboard.press('Tab');
  expect((await page.locator('.skip-link').boundingBox())?.y).toBeLessThan(0);
  await expect(page.getByText('eis_basic_qc', { exact: true })).toBeVisible();

  await page.getByLabel('Research question').fill('Run basic EIS quality checks');
  await page.getByRole('checkbox', { name: 'TypedTable' }).check();
  await page.getByRole('button', { name: 'Get routing decision' }).click();

  await expect(page.getByRole('heading', { name: 'Decision record' })).toBeVisible();
  await expect(page.getByText('eis_basic_qc', { exact: true })).toBeVisible();
  await expect(page.getByText('Run basic EIS quality checks', { exact: true })).toBeVisible();
  await audit(page, testInfo, 'workbench-desktop');
  await page.screenshot({ path: testInfo.outputPath('workbench-desktop.png'), fullPage: true });
});

test('research workbench remains usable on a narrow screen', async ({ browser }, testInfo) => {
  const context = await browser.newContext({ viewport: { width: 375, height: 812 } });
  const page = await context.newPage();
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Research workbench' })).toBeVisible();
  await expect(page.getByLabel('Research question')).toBeVisible();
  await audit(page, testInfo, 'workbench-mobile');
  await page.screenshot({ path: testInfo.outputPath('workbench-mobile.png'), fullPage: true });
  await context.close();
});

test('keyboard users meet the visible-focus and touch-target baseline', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Research workbench' })).toBeVisible();
  await page.getByLabel('Research question').fill('Check keyboard navigation for an EIS task');
  await page.evaluate(() => document.activeElement?.blur());

  const tabOrder = [
    page.locator('.skip-link'),
    page.locator('.brand'),
    page.getByRole('button', { name: 'Refresh' }),
    page.locator('.registry-list'),
    page.getByLabel('Research question'),
    page.getByRole('checkbox', { name: 'RawData' }),
    page.getByRole('checkbox', { name: 'TypedTable' }),
    page.getByRole('checkbox', { name: 'EISData' }),
    page.getByRole('checkbox', { name: 'EISQCReport' }),
    page.getByRole('checkbox', { name: 'Plot' }),
    page.getByRole('checkbox', { name: 'Decision' }),
    page.getByRole('checkbox', { name: 'Artifact' }),
    page.getByRole('button', { name: 'Get routing decision' }),
  ];

  for (const locator of tabOrder) {
    await page.keyboard.press('Tab');
    await expect(locator).toBeFocused();
    const metrics = await locator.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      return { width: rect.width, height: rect.height, outline: getComputedStyle(element).outlineWidth };
    });
    expect(metrics.width).toBeGreaterThanOrEqual(44);
    expect(metrics.height).toBeGreaterThanOrEqual(44);
    expect(metrics.outline).not.toBe('0px');
  }
});
