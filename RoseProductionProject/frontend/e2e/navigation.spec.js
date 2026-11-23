import { expect, test } from '@playwright/test';
import { connect, login, openModule } from './support.js';

const MODULES = [
  ['Farms', 'Farm'], ['Lots', 'Lot'], ['Rose varieties', 'RoseVariety'], ['Crops', 'Crop'],
  ['Seasons', 'Season'], ['Harvests', 'Harvest'], ['Forecasts', 'Forecast'],
];

test.describe('navigation with real data', () => {
  let counts;
  test.beforeAll(async () => {
    const conn = await connect();
    counts = {};
    for (const [, table] of MODULES) {
      const [[row]] = await conn.query(`SELECT COUNT(*) AS n FROM \`${table}\``);
      counts[table] = row.n;
    }
    const [[sum]] = await conn.query('SELECT COALESCE(SUM(quantity),0) AS total FROM Harvest');
    counts.total = Number(sum.total);
    await conn.end();
  });

  test('dashboard shows the database figures and charts', async ({ page }) => {
    const errors = [];
    page.on('pageerror', (e) => errors.push(String(e)));
    page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
    await login(page);
    const total = page.locator('article', { hasText: 'Total stems' });
    await expect(total).toContainText(counts.total.toLocaleString('en-US'));
    const records = page.locator('article', { hasText: 'Harvests' });
    await expect(records).toContainText(String(counts.Harvest));
    for (const title of ['Production by rose variety', 'Production by season', 'Harvest quantities over time', 'Forecast vs actual production', 'Upcoming seasons']) {
      await expect(page.getByRole('heading', { name: title })).toBeVisible();
    }
    await expect(page.locator('.recharts-surface').first()).toBeVisible();
    expect(errors).toEqual([]);
  });

  for (const [label, table] of MODULES) {
    test(`${label} lists every ${table} row`, async ({ page }) => {
      await login(page);
      await openModule(page, label);
      const word = counts[table] === 1 ? 'record' : 'records';
      await expect(page.locator('.table-card .result-count').last()).toHaveText(`${counts[table]} ${word}`);
    });
  }

  test('production analysis groups by season', async ({ page }) => {
    await login(page);
    await openModule(page, 'Production analysis');
    await page.getByLabel('Group by').selectOption('season');
    await expect(page.getByRole('heading', { name: 'Statistics by season' })).toBeVisible();
    const total = page.locator('article', { hasText: 'Total stems' });
    await expect(total).toContainText(counts.total.toLocaleString('en-US'));
  });

  test('harvest filters narrow the list', async ({ page }) => {
    const conn = await connect();
    const [[row]] = await conn.query('SELECT season_id, COUNT(*) AS n FROM Harvest GROUP BY season_id ORDER BY season_id LIMIT 1');
    await conn.end();
    await login(page);
    await openModule(page, 'Harvests');
    await page.getByRole('group', { name: 'Filters' }).getByLabel('Season').selectOption(String(row.season_id));
    const word = row.n === 1 ? 'record' : 'records';
    await expect(page.locator('.result-count')).toHaveText(`${row.n} ${word}`);
  });
});

test('forecast wizard fits a narrow window (685 px) without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 685, height: 914 });
  await login(page);
  await openModule(page, 'Forecasts');
  await page.getByRole('button', { name: 'Generate forecast' }).click();
  const dialog = page.getByRole('dialog', { name: 'Generate forecast' });
  const conn = await connect();
  const [[target]] = await conn.query(`SELECT h.crop_id, s.season_id, MAX(h.harvest_date) AS last
    FROM Harvest h JOIN Season s ON h.harvest_date BETWEEN s.start_date AND s.end_date
    GROUP BY h.crop_id, s.season_id HAVING COUNT(*) >= 3 ORDER BY h.crop_id LIMIT 1`);
  await conn.end();
  await dialog.getByLabel('Crop').selectOption(String(target.crop_id));
  await dialog.getByLabel('Season').selectOption(String(target.season_id));
  await dialog.getByLabel('Forecast date').fill(target.last);
  await dialog.getByRole('button', { name: 'Calculate estimate' }).click();
  await expect(dialog.locator('.forecast-result, .inline-error').first()).toBeVisible();
  const [scroll, client] = await page.evaluate(() => {
    const body = document.querySelector('.modal-body');
    return [body.scrollWidth, body.clientWidth];
  });
  expect(scroll).toBeLessThanOrEqual(client);
});
