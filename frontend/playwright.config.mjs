import { defineConfig, devices } from '@playwright/test';

const frontendPort = Number(process.env.MATFLOW_E2E_FRONTEND_PORT ?? 5173);

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    ...devices['Desktop Chrome'],
  },
  webServer: [
    {
      command: 'uv run python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001',
      cwd: '..',
      url: 'http://127.0.0.1:8001/docs',
      env: {
        MATFLOW_CORS_ORIGINS: `http://127.0.0.1:${frontendPort}`,
        MATFLOW_DATA_ROOT: 'frontend/test-results/runtime',
        MATFLOW_ALLOW_MODEL_MOCK: '1',
        MATFLOW_REVISION_MOCK_JSON: JSON.stringify({
          label: 'AI revised input',
          description: 'Imports the selected dataset with a reviewed, bounded table preview.',
          params: { file_name: 'measurement.csv', upload_id: '' },
          preview_spec: { version: '1.0', outputs: { raw: { renderer: 'table_head', max_rows: 5 } } },
          generated_code: null,
        }),
      },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${frontendPort}`,
      cwd: '.',
      url: `http://127.0.0.1:${frontendPort}`,
      env: { VITE_MATFLOW_API_URL: 'http://127.0.0.1:8001/api' },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
