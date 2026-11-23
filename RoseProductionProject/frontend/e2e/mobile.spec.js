import { expect, test } from '@playwright/test';
import { login, openModule } from './support.js';

test.describe('responsive layout (Pixel 7)', () => {
  test('sidebar collapses into a menu and pages stay usable', async ({ page }) => {
    await login(page);
    const nav = page.getByRole('complementary', { name: 'Main navigation' });
    await expect(nav).not.toBeInViewport();
    await page.getByRole('button', { name: 'Open menu' }).click();
    await expect(nav).toBeInViewport();
    await nav.getByRole('link', { name: 'Harvests', exact: true }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Harvests' })).toBeVisible();
    await expect(nav).not.toBeInViewport();

    // Tables become stacked cards: header row hidden, labels shown per cell.
    await expect(page.locator('.data-table thead').first()).toBeHidden();
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    const viewport = page.viewportSize().width;
    expect(width).toBeLessThanOrEqual(viewport + 1);

    await page.getByRole('button', { name: 'New harvest' }).click();
    await expect(page.getByRole('dialog', { name: 'New harvest' })).toBeInViewport();
    await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click();
  });

  test('dashboard renders on a phone without horizontal scrolling', async ({ page }) => {
    await login(page);
    await expect(page.getByText('Production by rose variety')).toBeVisible();
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(width).toBeLessThanOrEqual(page.viewportSize().width + 1);
    await openModule(page, 'Forecasts');
    await expect(page.getByRole('button', { name: 'Generate forecast' })).toBeVisible();
  });
});
