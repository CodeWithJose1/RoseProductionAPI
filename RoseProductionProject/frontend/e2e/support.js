// Helpers for the E2E suite. Credentials are read at run time from the
// backend .env file (never stored in the test sources or the GUI).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import mysql from 'mysql2/promise';

const here = path.dirname(fileURLToPath(import.meta.url));

function parseEnv(file) {
  const out = {};
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (match) out[match[1]] = match[2].replace(/^['"]|['"]$/g, '');
  }
  return out;
}

export function loadEnv() {
  const candidates = [
    process.env.ROSE_ENV_FILE,
    path.resolve(here, '../../.env'), // RoseProductionAPI/.env
    path.resolve(here, '../../../.env'),
  ].filter(Boolean);
  const file = candidates.find((f) => fs.existsSync(f));
  if (!file) throw new Error('Backend .env not found (set ROSE_ENV_FILE)');
  return { ...parseEnv(file), ...process.env };
}

export async function connect() {
  const env = loadEnv();
  return mysql.createConnection({
    host: env.DB_HOST, port: Number(env.DB_PORT || 3306), user: env.DB_USER,
    password: env.DB_PASSWORD, database: env.DB_NAME, dateStrings: true, decimalNumbers: true,
  });
}

export const TABLES = {
  Farm: 'farm_id', Lot: 'lot_id', RoseVariety: 'variety_id', Crop: 'crop_id',
  Season: 'season_id', Harvest: 'harvest_id', Forecast: 'forecast_id',
};
export const DELETE_ORDER = ['Forecast', 'Harvest', 'Crop', 'Season', 'Lot', 'RoseVariety', 'Farm'];

export async function snapshot(conn) {
  const result = {};
  for (const [table, pk] of Object.entries(TABLES)) {
    const [rows] = await conn.query(`SELECT * FROM \`${table}\` ORDER BY \`${pk}\``);
    result[table] = Object.fromEntries(rows.map((row) => [row[pk], JSON.stringify(row)]));
  }
  return result;
}

export const SNAPSHOT_FILE = path.resolve(here, '../test-results/e2e-baseline.json');

/** Deletes only ids created by the tests (never ids from the baseline). */
export async function cleanup(conn, created) {
  const baseline = JSON.parse(fs.readFileSync(SNAPSHOT_FILE, 'utf8'));
  for (const table of DELETE_ORDER) {
    const ids = [...(created[table] || [])].filter((id) => !(String(id) in baseline[table]));
    if (ids.length) {
      await conn.query(`DELETE FROM \`${table}\` WHERE \`${TABLES[table]}\` IN (?)`, [ids]);
    }
  }
}

export async function login(page) {
  const env = loadEnv();
  await page.goto('/app/');
  await page.getByLabel('Access key').fill(env.API_KEY);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByRole('heading', { level: 1, name: 'Dashboard' }).waitFor();
}

export async function openModule(page, label) {
  const nav = page.getByRole('complementary', { name: 'Main navigation' });
  const onScreen = await nav.evaluate((el) => el.getBoundingClientRect().right > 0);
  if (!onScreen) {
    await page.getByRole('button', { name: 'Open menu' }).click();
    await page.waitForFunction(() => document.querySelector('.sidebar').getBoundingClientRect().left >= 0);
  }
  await nav.getByRole('link', { name: label, exact: true }).click();
  await page.getByRole('heading', { level: 1, name: label }).waitFor();
}
