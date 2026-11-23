import { expect, test } from '@playwright/test';
import { loadEnv, login } from './support.js';

test.describe('authentication', () => {
  test('rejects a wrong access key', async ({ page }) => {
    await page.goto('/app/');
    await page.getByLabel('Access key').fill('definitely-wrong');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByText('Invalid access key')).toBeVisible();
  });

  test('protected API calls without a session return 401', async ({ request }) => {
    const response = await request.get('/farms');
    expect(response.status()).toBe(401);
  });

  test('signs in, survives a reload and signs out', async ({ page, context }) => {
    await login(page);
    const cookies = await context.cookies();
    const session = cookies.find((c) => c.name === 'rose_session');
    expect(session.httpOnly).toBe(true);
    expect(session.sameSite).toBe('Strict');

    await page.reload();
    await expect(page.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeVisible();

    await page.getByRole('button', { name: 'Sign out' }).click();
    await expect(page.getByLabel('Access key')).toBeVisible();
    await page.reload();
    await expect(page.getByLabel('Access key')).toBeVisible();
  });

  test('the API key never reaches browser storage, HTML or scripts', async ({ page }) => {
    const { API_KEY } = loadEnv();
    const bodies = [];
    page.on('response', async (response) => {
      const type = response.headers()['content-type'] || '';
      if (/javascript|html|css|json/.test(type)) bodies.push(await response.text().catch(() => ''));
    });
    await login(page);
    const storage = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }) + document.cookie + document.documentElement.outerHTML);
    expect(storage).not.toContain(API_KEY);
    for (const body of bodies) expect(body).not.toContain(API_KEY);
  });
});
