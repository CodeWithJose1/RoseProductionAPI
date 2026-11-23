// Duplicate prevention through the real GUI (2026-11-23), verified in MySQL:
// a duplicate is refused with a clear message, the typed values stay in the
// form, repeated activations of the submit button send one request, and the
// row count does not change. Every record created here is deleted by id.
import { expect, test } from '@playwright/test';
import { cleanup, connect, login, openModule } from './support.js';

test.describe.configure({ mode: 'serial' });

const stamp = Date.now().toString(36);
const created = { Farm: [], Lot: [], RoseVariety: [], Season: [] };
let conn;

test.beforeAll(async () => { conn = await connect(); });
test.afterAll(async () => { await cleanup(conn, created); await conn.end(); });

async function count(sql, params) {
  const [rows] = await conn.query(sql, params);
  return Number(Object.values(rows[0])[0]);
}

function trackPosts(page, path) {
  const sent = [];
  page.on('request', (r) => {
    if (r.method() === 'POST' && new URL(r.url()).pathname === path) sent.push(r.postData());
  });
  return sent;
}

test('variety: duplicate name refused by the API is shown and the input is kept', async ({ page }) => {
  const name = `E2E_Dup_${stamp}`;
  await login(page);
  await openModule(page, 'Rose varieties');
  const posts = trackPosts(page, '/varieties');

  await page.getByRole('button', { name: 'New variety' }).click();
  let form = page.getByRole('dialog', { name: 'New variety' });
  await form.getByLabel('Variety name').fill(name);
  await form.getByLabel('Color').fill('Red');
  await form.getByRole('button', { name: 'Create variety' }).click();
  await expect(form).toBeHidden();
  const [row] = (await conn.query('SELECT variety_id FROM RoseVariety WHERE name = ?', [name]))[0];
  created.RoseVariety.push(row.variety_id);

  // A second variety with the same name created by someone else after the
  // list was loaded is invisible to the client-side check: the API decides.
  const other = `E2E_Dup2_${stamp}`;
  const response = await page.request.post('/varieties', {
    data: { name: other, color: 'White' },
    headers: { 'X-Requested-With': 'RoseProductionGUI' },
  });
  expect(response.status()).toBe(201);
  created.RoseVariety.push((await response.json()).variety.variety_id);

  const before = await count('SELECT COUNT(*) FROM RoseVariety WHERE name IN (?, ?)', [name, other]);
  await page.getByRole('button', { name: 'New variety' }).click();
  form = page.getByRole('dialog', { name: 'New variety' });
  await form.getByLabel('Variety name').fill(`  ${other.toUpperCase()}  `);
  await form.getByLabel('Color').fill('Pink');
  await form.getByRole('button', { name: 'Create variety' }).click();
  await expect(form.getByText(/A rose variety with this name already exists/).first()).toBeVisible();
  await expect(form.getByLabel('Variety name')).toHaveValue(`  ${other.toUpperCase()}  `);
  await expect(form.getByLabel('Color')).toHaveValue('Pink');
  await expect(form.getByRole('button', { name: 'Create variety' })).toBeEnabled();
  expect(await count('SELECT COUNT(*) FROM RoseVariety WHERE name IN (?, ?)', [name, other])).toBe(before);

  // The duplicate the page can already see is flagged without a request.
  const sentBefore = posts.length;
  await page.getByRole('button', { name: 'Cancel' }).click();
  await page.getByRole('button', { name: 'New variety' }).click();
  form = page.getByRole('dialog', { name: 'New variety' });
  await form.getByLabel('Variety name').fill(name.toLowerCase());
  await form.getByLabel('Color').fill('Red');
  await form.getByRole('button', { name: 'Create variety' }).click();
  await expect(form.getByText('A rose variety with this name already exists.')).toBeVisible();
  expect(posts.length).toBe(sentBefore);
  await page.getByRole('button', { name: 'Cancel' }).click();
});

test('farm: two activations in the same task send one request and create one row', async ({ page }) => {
  const name = `E2E_DblFarm_${stamp}`;
  await login(page);
  await openModule(page, 'Farms');
  const posts = trackPosts(page, '/farms');
  await page.getByRole('button', { name: 'New farm' }).click();
  const form = page.getByRole('dialog', { name: 'New farm' });
  await form.getByLabel('Farm name').fill(name);
  await form.getByLabel('Location').fill('E2E location');
  await form.getByRole('button', { name: 'Create farm' }).dblclick();
  await page.evaluate(() => {
    const button = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Create farm');
    const formEl = document.getElementById('resource-form');
    if (button) { button.click(); button.click(); }
    if (formEl) formEl.requestSubmit();
  });
  await expect(form).toBeHidden();
  await page.waitForTimeout(500);
  const ids = (await conn.query('SELECT farm_id FROM Farm WHERE name = ?', [name]))[0].map((r) => r.farm_id);
  created.Farm.push(...ids);
  expect(posts.length).toBe(1);
  expect(ids).toHaveLength(1);
});

test('lot: the same name is refused inside a farm and accepted in another farm', async ({ page }) => {
  const farmA = (await conn.query('INSERT INTO Farm (name, location) VALUES (?, ?)', [`E2E_FarmA_${stamp}`, 'E2E']))[0].insertId;
  const farmB = (await conn.query('INSERT INTO Farm (name, location) VALUES (?, ?)', [`E2E_FarmB_${stamp}`, 'E2E']))[0].insertId;
  created.Farm.push(farmA, farmB);
  await login(page);
  await openModule(page, 'Lots');
  const create = async (farmName, lotName) => {
    await page.getByRole('button', { name: 'New lot' }).click();
    const form = page.getByRole('dialog', { name: 'New lot' });
    await form.getByLabel('Farm').selectOption({ label: `${farmName} — E2E` });
    await form.getByLabel('Lot name').fill(lotName);
    await form.getByLabel('Area').fill('1.5');
    await form.getByRole('button', { name: 'Create lot' }).click();
    return form;
  };
  let form = await create(`E2E_FarmA_${stamp}`, 'E2E Lot');
  await expect(form).toBeHidden();
  form = await create(`E2E_FarmA_${stamp}`, ' e2e   LOT ');
  await expect(form.getByText('This lot already exists in the selected farm.')).toBeVisible();
  await page.getByRole('button', { name: 'Cancel' }).click();
  form = await create(`E2E_FarmB_${stamp}`, 'E2E Lot');
  await expect(form).toBeHidden();
  const lots = (await conn.query('SELECT lot_id, farm_id, name FROM Lot WHERE farm_id IN (?, ?) ORDER BY lot_id', [farmA, farmB]))[0];
  created.Lot.push(...lots.map((l) => l.lot_id));
  expect(lots.map((l) => [l.farm_id, l.name])).toEqual([[farmA, 'E2E Lot'], [farmB, 'E2E Lot']]);
});
