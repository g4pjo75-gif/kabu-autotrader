import { test as base, expect } from '@playwright/test';
import * as path from 'path';

/**
 * Custom fixtures for role-based authenticated pages.
 *
 * Usage:
 *   import { test, expect } from '../fixtures';
 *
 *   test('user can see dashboard', async ({ userPage }) => {
 *     await userPage.goto('/dashboard');
 *     await expect(userPage.getByRole('heading')).toBeVisible();
 *   });
 */

const authDir = path.join(process.cwd(), 'playwright', '.auth');

type Fixtures = {
  userPage: import('@playwright/test').Page;
  adminPage: import('@playwright/test').Page;
};

export const test = base.extend<Fixtures>({
  userPage: async ({ browser }, use) => {
    const context = await browser.newContext({
      storageState: path.join(authDir, 'user.json'),
    });
    const page = await context.newPage();
    await use(page);
    await context.close();
  },

  adminPage: async ({ browser }, use) => {
    const context = await browser.newContext({
      storageState: path.join(authDir, 'admin.json'),
    });
    const page = await context.newPage();
    await use(page);
    await context.close();
  },
});

export { expect };
