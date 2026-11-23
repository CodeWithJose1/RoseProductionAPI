// Captures the documentation screenshots (docs/screenshots/*.png) from the
// running application. Usage: node scripts/screenshots.mjs  (API on :7003)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, devices } from '@playwright/test';
import { loadEnv } from '../e2e/support.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(here, '../../docs/screenshots');
const base = process.env.ROSE_BASE_URL || 'http://127.0.0.1:7003';
fs.mkdirSync(out, { recursive: true });
const { API_KEY } = loadEnv();

async function signIn(page) {
  await page.goto(`${base}/app/`);
  await page.getByLabel('Access key').fill(API_KEY);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByRole('heading', { level: 1, name: 'Dashboard' }).waitFor();
}

const shot = (page, name, full = true) => page.screenshot({ path: path.join(out, `${name}.png`), fullPage: full });

const browser = await chromium.launch();
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const page = await context.newPage();
  await page.goto(`${base}/app/`);
  await page.getByLabel('Access key').waitFor();
  await shot(page, '01-login', false);
  await signIn(page);
  await page.waitForTimeout(800);
  await shot(page, '02-dashboard');

  const pages = [['farms', '03-farms'], ['lots', '04-lots'], ['varieties', '05-varieties'], ['crops', '06-crops'],
    ['seasons', '07-seasons'], ['harvests', '08-harvests'], ['forecasts', '10-forecasts'], ['analytics', '12-analytics']];
  for (const [route, name] of pages) {
    await page.goto(`${base}/app/${route}`);
    await page.locator('h1').waitFor();
    await page.waitForTimeout(700);
    await shot(page, name);
  }

  // Harvest form with validation messages (nothing is submitted).
  await page.goto(`${base}/app/harvests`);
  await page.getByRole('button', { name: 'New harvest' }).click();
  const form = page.getByRole('dialog', { name: 'New harvest' });
  await form.getByLabel('Crop').selectOption({ index: 1 });
  await form.getByLabel('Season').selectOption({ index: 1 });
  await form.getByLabel('Harvest date').fill('2030-01-01');
  await form.getByLabel('Quantity (stems)').fill('0');
  await form.getByRole('button', { name: 'Create harvest' }).click();
  await page.waitForTimeout(300);
  await shot(page, '09-harvest-validation', false);
  await form.getByRole('button', { name: 'Cancel' }).click();

  // Forecast generation preview (calculated, NOT saved).
  await page.goto(`${base}/app/forecasts`);
  await page.getByRole('button', { name: 'Generate forecast' }).click();
  const gen = page.getByRole('dialog', { name: 'Generate forecast' });
  await gen.getByLabel('Crop').selectOption('1');
  await gen.getByLabel('Season').selectOption('1');
  await gen.getByLabel('Forecast date').fill('2026-02-12');
  await gen.getByRole('button', { name: 'Calculate estimate' }).click();
  await gen.locator('.forecast-result').waitFor();
  await shot(page, '11-forecast-generate', false);
  await gen.getByRole('button', { name: 'Cancel' }).click();
  await context.close();

  const mobile = await browser.newContext({ ...devices['Pixel 7'] });
  const phone = await mobile.newPage();
  await signIn(phone);
  await phone.waitForTimeout(600);
  await shot(phone, '13-mobile-dashboard', false);
  await phone.getByRole('button', { name: 'Open menu' }).click();
  await phone.waitForTimeout(300);
  await shot(phone, '14-mobile-menu', false);
  await mobile.close();
  console.log(`Screenshots written to ${out}`);
} finally {
  await browser.close();
}
