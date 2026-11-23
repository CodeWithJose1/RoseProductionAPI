// Workflows A-D of the project brief, executed through the GUI and verified
// directly in MySQL. Every record created here is deleted again (through the
// GUI where the workflow says so, otherwise by id in afterAll).
import { expect, test } from '@playwright/test';
import { cleanup, connect, login, openModule } from './support.js';

test.describe.configure({ mode: 'serial' });

const stamp = Date.now().toString(36);
const created = { RoseVariety: [], Crop: [], Harvest: [], Forecast: [] };
let conn;
let shared = {};

test.beforeAll(async () => {
  conn = await connect();
});

test.afterAll(async () => {
  await cleanup(conn, created);
  await conn.end();
});

async function one(sql, params) {
  const [rows] = await conn.query(sql, params);
  return rows[0];
}

function dialog(page, name) {
  return name ? page.getByRole('dialog', { name }) : page.getByRole('dialog');
}

test('Workflow A — register, edit and delete a rose variety', async ({ page }) => {
  const name = `E2E_Variety_${stamp}`;
  await login(page);
  await openModule(page, 'Rose varieties');

  await page.getByRole('button', { name: 'New variety' }).click();
  const form = dialog(page, 'New variety');
  await form.getByLabel('Variety name').fill(name);
  await form.getByLabel('Color').fill('Purple');
  await form.getByRole('button', { name: 'Create variety' }).click();
  await expect(page.getByText('Variety created successfully')).toBeVisible();
  await expect(page.getByRole('cell', { name, exact: true })).toBeVisible();

  const row = await one('SELECT * FROM RoseVariety WHERE name = ?', [name]);
  expect(row).toMatchObject({ name, color: 'Purple' });
  created.RoseVariety.push(row.variety_id);

  await page.getByRole('button', { name: `Edit ${name}` }).click();
  const edit = dialog(page, 'Edit variety');
  await edit.getByLabel('Variety name').fill(`${name}_Updated`);
  await edit.getByLabel('Color').fill('Red');
  await edit.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('cell', { name: `${name}_Updated`, exact: true })).toBeVisible();
  const updated = await one('SELECT * FROM RoseVariety WHERE variety_id = ?', [row.variety_id]);
  expect(updated).toMatchObject({ name: `${name}_Updated`, color: 'Red' });

  await page.getByRole('button', { name: `Delete ${name}_Updated` }).click();
  await dialog(page, 'Delete variety?').getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByText('Variety deleted successfully')).toBeVisible();
  await expect(page.getByRole('cell', { name: `${name}_Updated`, exact: true })).toHaveCount(0);
  expect(await one('SELECT * FROM RoseVariety WHERE variety_id = ?', [row.variety_id])).toBeUndefined();
});

test('Workflow B — register a crop on an existing lot and variety', async ({ page }) => {
  const lot = await one('SELECT lot_id FROM Lot ORDER BY lot_id LIMIT 1');
  const variety = await one('SELECT variety_id FROM RoseVariety ORDER BY variety_id LIMIT 1');
  // A season that has already started: the crop is planted on its first day
  // so that Workflow C can register a (non-future) harvest inside it.
  const season = await one(`SELECT * FROM Season WHERE start_date <= CURDATE()
                            ORDER BY DATEDIFF(LEAST(end_date, CURDATE()), start_date) DESC LIMIT 1`);
  expect(season, 'needs a season that has started').toBeTruthy();
  const plantingDate = season.start_date;
  const [[{ maxId }]] = await conn.query('SELECT COALESCE(MAX(crop_id), 0) AS maxId FROM Crop');

  await login(page);
  await openModule(page, 'Crops');
  await page.getByRole('button', { name: 'New crop' }).click();
  const form = dialog(page, 'New crop');
  await form.getByLabel('Lot').selectOption(String(lot.lot_id));
  await form.getByLabel('Rose variety').selectOption(String(variety.variety_id));
  await form.getByLabel('Planting date').fill(plantingDate);
  await form.getByRole('button', { name: 'Create crop' }).click();
  await expect(page.getByText('Crop created successfully')).toBeVisible();

  const crop = await one('SELECT * FROM Crop WHERE crop_id > ? AND lot_id = ? AND variety_id = ? AND planting_date = ?',
    [maxId, lot.lot_id, variety.variety_id, plantingDate]);
  expect(crop).toBeTruthy();
  created.Crop.push(crop.crop_id);
  shared.crop = crop;
  shared.season = season;

  // Persisted: still listed after a full browser reload.
  await page.reload();
  await page.getByRole('heading', { level: 1, name: 'Crops' }).waitFor();
  await page.getByPlaceholder('Search crops…').fill(`${crop.crop_id} `);
  await expect(page.getByRole('cell', { name: String(crop.crop_id), exact: true })).toBeVisible();
});

test('Workflow C — register a harvest and reject an out-of-season date', async ({ page }) => {
  expect(shared.crop, 'Workflow B must run first').toBeTruthy();
  const { season } = shared;
  const [[{ today }]] = await conn.query('SELECT CURDATE() AS today');
  const validDate = season.end_date < today ? season.end_date : today; // never in the future
  const quantity = 777;

  await login(page);
  await openModule(page, 'Harvests');
  await page.getByRole('button', { name: 'New harvest' }).click();
  let form = dialog(page, 'New harvest');
  await form.getByLabel('Crop').selectOption(String(shared.crop.crop_id));
  await form.getByLabel('Season').selectOption(String(season.season_id));
  await form.getByLabel('Harvest date').fill(validDate);
  await form.getByLabel('Quantity (stems)').fill(String(quantity));
  await form.getByRole('button', { name: 'Create harvest' }).click();
  await expect(page.getByText('Harvest created successfully')).toBeVisible();

  const harvest = await one('SELECT * FROM Harvest WHERE crop_id = ? AND harvest_date = ? AND quantity = ?',
    [shared.crop.crop_id, validDate, quantity]);
  expect(harvest).toMatchObject({ season_id: season.season_id });
  created.Harvest.push(harvest.harvest_id);

  // Invalid: a date outside the selected season is explained and not saved.
  const outside = await one('SELECT DATE_ADD(end_date, INTERVAL 1 DAY) AS d FROM Season WHERE season_id = ?', [season.season_id]);
  await page.getByRole('button', { name: 'New harvest' }).click();
  form = dialog(page, 'New harvest');
  await form.getByLabel('Crop').selectOption(String(shared.crop.crop_id));
  await form.getByLabel('Season').selectOption(String(season.season_id));
  await form.getByLabel('Harvest date').fill(outside.d);
  await form.getByLabel('Quantity (stems)').fill('0');
  await form.getByRole('button', { name: 'Create harvest' }).click();
  await expect(form.getByText(`The date must be inside ${season.name}`)).toBeVisible();
  await expect(form.getByText('Quantity must be greater than zero')).toBeVisible();
  await form.getByRole('button', { name: 'Cancel' }).click();
  const [[count]] = await conn.query('SELECT COUNT(*) AS n FROM Harvest WHERE crop_id = ? AND harvest_date = ?',
    [shared.crop.crop_id, outside.d]);
  expect(count.n).toBe(0);
});

test('Workflow C (edit) — moving a harvest to a season that excludes its date is refused', async ({ page }) => {
  const harvestId = created.Harvest[0];
  const other = await one(`SELECT s.* FROM Season s, Harvest h WHERE h.harvest_id = ?
                           AND h.harvest_date NOT BETWEEN s.start_date AND s.end_date LIMIT 1`, [harvestId]);
  test.skip(!other, 'needs a second season that excludes the harvest date');
  await login(page);
  await openModule(page, 'Harvests');
  await page.getByPlaceholder('Search harvests…').fill('777');
  await page.getByRole('button', { name: new RegExp(`^Edit Harvest #${harvestId} `) }).click();
  const form = dialog(page, 'Edit harvest');
  await form.getByLabel('Season').selectOption(String(other.season_id));
  await form.getByRole('button', { name: 'Save changes' }).click();
  await expect(form.getByText(`The date must be inside ${other.name}`)).toBeVisible();
  await form.getByRole('button', { name: 'Cancel' }).click();
  const row = await one('SELECT season_id FROM Harvest WHERE harvest_id = ?', [harvestId]);
  expect(row.season_id).not.toBe(other.season_id);
});

function pickForecastTarget(harvests, forecasts, seasons, plantingByCrop) {
  const byCrop = new Map();
  for (const h of harvests) {
    if (!byCrop.has(h.crop_id)) byCrop.set(h.crop_id, []);
    byCrop.get(h.crop_id).push(h);
  }
  const taken = new Set(forecasts.map((f) => `${f.crop_id}|${f.forecast_date}`));
  for (const [cropId, list] of byCrop) {
    list.sort((a, b) => (a.harvest_date < b.harvest_date ? -1 : a.harvest_date > b.harvest_date ? 1 : a.harvest_id - b.harvest_id));
    if (list.length < 3) continue;
    for (const season of seasons) {
      for (let d = new Date(`${season.start_date}T00:00:00Z`); d <= new Date(`${season.end_date}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + 1)) {
        const iso = d.toISOString().slice(0, 10);
        if (iso < plantingByCrop[cropId]) continue;
        const previous = list.filter((h) => h.harvest_date < iso);
        if (previous.length >= 3 && !taken.has(`${cropId}|${iso}`)) {
          const last3 = previous.slice(-3);
          const estimate = Math.round((last3.reduce((s, h) => s + h.quantity, 0) / 3) * 100) / 100;
          return { cropId, season, date: iso, estimate, last3 };
        }
      }
    }
  }
  return null;
}

test('Workflow D — generate, save and display a forecast from real history', async ({ page }) => {
  const [harvests] = await conn.query('SELECT harvest_id, crop_id, harvest_date, quantity FROM Harvest');
  const [forecasts] = await conn.query('SELECT crop_id, forecast_date FROM Forecast');
  const [seasons] = await conn.query('SELECT * FROM Season ORDER BY start_date');
  const [crops] = await conn.query('SELECT crop_id, planting_date FROM Crop');
  const plantingByCrop = Object.fromEntries(crops.map((c) => [c.crop_id, c.planting_date]));
  const target = pickForecastTarget(harvests, forecasts, seasons, plantingByCrop);
  expect(target, 'needs a crop with at least 3 harvests').toBeTruthy();

  await login(page);
  await openModule(page, 'Forecasts');
  await page.getByRole('button', { name: 'Generate forecast' }).click();
  const form = dialog(page, 'Generate forecast');
  await form.getByLabel('Crop').selectOption(String(target.cropId));
  await form.getByLabel('Season').selectOption(String(target.season.season_id));
  await form.getByLabel('Forecast date').fill(target.date);
  await form.getByRole('button', { name: 'Calculate estimate' }).click();
  const expected = target.estimate.toLocaleString('en-US', { maximumFractionDigits: 2 });
  await expect(form.getByText(`${expected} stems`)).toBeVisible();
  await expect(form.locator('.forecast-result tbody tr')).toHaveCount(3);

  await form.getByRole('button', { name: 'Save forecast' }).click();
  await expect(form.getByText(/Saved as forecast #\d+/)).toBeVisible();

  const row = await one('SELECT * FROM Forecast WHERE crop_id = ? AND forecast_date = ?', [target.cropId, target.date]);
  expect(row).toMatchObject({
    season_id: target.season.season_id, estimated_quantity: target.estimate, method: 'Moving Average (3 records)',
  });
  created.Forecast.push(row.forecast_id);

  await form.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByPlaceholder('Search forecasts…').fill(target.date);
  const tableRow = page.locator('tbody tr', { hasText: `#${target.cropId} ·` }).filter({ hasText: expected });
  await expect(tableRow).toBeVisible();
  const status = await one('SELECT forecast_status FROM vw_forecast_status WHERE forecast_id = ?', [row.forecast_id]);
  await expect(tableRow).toContainText(status.forecast_status);

  // Delete it through the GUI as well.
  await tableRow.getByRole('button', { name: /^Delete Forecast/ }).click();
  await dialog(page, 'Delete forecast?').getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByText('Forecast deleted successfully')).toBeVisible();
  expect(await one('SELECT * FROM Forecast WHERE forecast_id = ?', [row.forecast_id])).toBeUndefined();
});

test('Clean-up through the GUI — delete the test harvest and crop', async ({ page }) => {
  await login(page);
  await openModule(page, 'Harvests');
  await page.getByPlaceholder('Search harvests…').fill('777');
  for (const id of created.Harvest) {
    await page.getByRole('button', { name: new RegExp(`^Delete Harvest #${id} `) }).click();
    await dialog(page, 'Delete harvest?').getByRole('button', { name: 'Delete' }).click();
    await expect(page.getByText('Harvest deleted successfully')).toBeVisible();
  }
  await openModule(page, 'Crops');
  for (const id of created.Crop) {
    await page.getByPlaceholder('Search crops…').fill(`${id} `);
    await page.getByRole('button', { name: new RegExp(`^Delete Crop #${id} `) }).click();
    await dialog(page, 'Delete crop?').getByRole('button', { name: 'Delete' }).click();
    await expect(page.getByText('Crop deleted successfully')).toBeVisible();
  }
  const [[h]] = await conn.query('SELECT COUNT(*) AS n FROM Harvest WHERE harvest_id IN (?)', [created.Harvest]);
  const [[c]] = await conn.query('SELECT COUNT(*) AS n FROM Crop WHERE crop_id IN (?)', [created.Crop]);
  expect(h.n + c.n).toBe(0);
});
