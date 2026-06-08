import { defineConfig, devices } from '@playwright/test';
import * as path from 'path';

/**
 * Playwright configuration for docker-test-loop
 *
 * Features:
 * - Video recording on all tests
 * - Screenshot on failure
 * - Full trace recording
 * - HAR network capture
 * - Console log collection
 * - storageState session persistence (auth.setup.ts)
 * - Shard-based parallel execution with blob reporter
 */

// Log directory for current run
const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
const logDir = path.join(process.cwd(), '.test-logs', timestamp);

export default defineConfig({
  // Test directory
  testDir: './tests/e2e',

  // Output directory for test artifacts
  outputDir: path.join(logDir, 'browser'),

  // Fail the build on CI if you accidentally left test.only in the source code
  forbidOnly: !!process.env.CI,

  // Fully parallel execution
  fullyParallel: true,

  // Retry on CI only
  retries: process.env.CI ? 2 : 0,

  // CI: 2 workers per shard, local: auto
  workers: process.env.CI ? 2 : undefined,

  // Reporter to use
  reporter: [
    ['html', { outputFolder: path.join(logDir, 'reports', 'html') }],
    ['json', { outputFile: path.join(logDir, 'tests', 'e2e-results.json') }],
    ['blob', { outputDir: path.join(logDir, 'blob-report') }],
    ['list'],
  ],

  // Shared settings for all projects
  use: {
    // Base URL for relative navigation
    baseURL: process.env.BASE_URL || 'http://localhost:3000',

    // Collect trace when retrying the failed test
    trace: 'on',

    // Record video for all tests
    video: 'on',

    // Take screenshot on failure
    screenshot: 'only-on-failure',

    // Timeout for each action
    actionTimeout: 10000,

    // Timeout for navigation
    navigationTimeout: 30000,
  },

  // Configure projects for major browsers
  projects: [
    // Authentication setup - runs once before all browser projects
    {
      name: 'setup',
      testMatch: /.*\.setup\.ts/,
    },

    {
      name: 'chromium',
      testMatch: /.*\.pw\.ts/,
      testIgnore: /.*\.test\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'playwright/.auth/user.json',
        serviceWorkers: 'block',
        viewport: { width: 1280, height: 720 },
      },
      dependencies: ['setup'],
    },

    {
      name: 'firefox',
      testMatch: /.*\.pw\.ts/,
      testIgnore: /.*\.test\.ts/,
      use: {
        ...devices['Desktop Firefox'],
        storageState: 'playwright/.auth/user.json',
      },
      dependencies: ['setup'],
    },

    {
      name: 'webkit',
      testMatch: /.*\.pw\.ts/,
      testIgnore: /.*\.test\.ts/,
      use: {
        ...devices['Desktop Safari'],
        storageState: 'playwright/.auth/user.json',
      },
      dependencies: ['setup'],
    },

    // Mobile viewports
    {
      name: 'Mobile Chrome',
      testMatch: /.*\.pw\.ts/,
      testIgnore: /.*\.test\.ts/,
      use: {
        ...devices['Pixel 5'],
        storageState: 'playwright/.auth/user.json',
      },
      dependencies: ['setup'],
    },

    {
      name: 'Mobile Safari',
      testMatch: /.*\.pw\.ts/,
      testIgnore: /.*\.test\.ts/,
      use: {
        ...devices['iPhone 12'],
        storageState: 'playwright/.auth/user.json',
      },
      dependencies: ['setup'],
    },
  ],

  // Run your local dev server before starting the tests
  webServer: process.env.NO_SERVER ? undefined : {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
  },

  // Global setup and teardown
  globalSetup: './tests/e2e/global-setup.ts',
  globalTeardown: './tests/e2e/global-teardown.ts',

  // Test timeout
  timeout: 60 * 1000,

  // Expect timeout
  expect: {
    timeout: 10 * 1000,
  },

  // Metadata for reports
  metadata: {
    project: process.env.PROJECT_NAME || 'CCAGI Project',
    environment: process.env.NODE_ENV || 'test',
    timestamp: timestamp,
  },
});

// Export log directory for use in tests
export const TEST_LOG_DIR = logDir;
