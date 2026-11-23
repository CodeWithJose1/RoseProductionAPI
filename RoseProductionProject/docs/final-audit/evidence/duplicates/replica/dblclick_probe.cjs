// Probe: does the CURRENT GUI send more than one POST when the submit button is
// double-clicked or when Enter is pressed twice? Runs against the replica API.
const { chromium } = require('/home/claude/rose/frontend/node_modules/playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const posts = [];
  page.on('request', (r) => { if (r.method() === 'POST' && /\/varieties$/.test(r.url())) posts.push(r.postData()); });
  await page.goto('http://127.0.0.1:7003/app/');
  await page.fill('#access-key', process.env.API_KEY);
  await page.click('button[type=submit]');
  await page.getByRole('heading', { name: 'Dashboard', level: 1 }).waitFor();
  await page.goto('http://127.0.0.1:7003/app/varieties');
  await page.locator('h1').waitFor();
  const tag = 'DBLPROBE_' + Date.now();
  const results = {};
  // 1) double click on the submit button
  await page.getByRole('button', { name: 'New variety' }).click();
  await page.getByLabel('Variety name').fill(tag + '_dbl');
  await page.getByLabel('Color').fill('Red');
  await page.getByRole('button', { name: 'Create variety' }).dblclick();
  await page.waitForTimeout(1500);
  results.dblclick_posts = posts.length;
  // 2) Enter pressed twice quickly in a text field
  posts.length = 0;
  await page.getByRole('button', { name: 'New variety' }).click();
  await page.getByLabel('Variety name').fill(tag + '_enter');
  await page.getByLabel('Color').fill('Red');
  await page.getByLabel('Color').press('Enter');
  await page.getByLabel('Color').press('Enter').catch(() => {});
  await page.waitForTimeout(1500);
  results.enter_twice_posts = posts.length;
  // 3) two clicks dispatched in the same task (synthetic, faster than a human)
  posts.length = 0;
  if (!(await page.getByRole('button', { name: 'New variety' }).isVisible())) await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'New variety' }).click();
  await page.getByLabel('Variety name').fill(tag + '_sync');
  await page.getByLabel('Color').fill('Red');
  await page.evaluate(() => { const b = [...document.querySelectorAll('button')].find(x => x.textContent.trim() === 'Create variety'); b.click(); b.click(); });
  await page.waitForTimeout(1500);
  results.same_task_two_clicks_posts = posts.length;
  // 4) requestSubmit twice in the same task
  posts.length = 0;
  if (!(await page.getByRole('button', { name: 'New variety' }).isVisible())) await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'New variety' }).click();
  await page.getByLabel('Variety name').fill(tag + '_req');
  await page.getByLabel('Color').fill('Red');
  await page.evaluate(() => { const f = document.getElementById('resource-form'); f.requestSubmit(); f.requestSubmit(); });
  await page.waitForTimeout(1500);
  results.same_task_two_submits_posts = posts.length;
  // rows created
  const list = await page.evaluate(async () => (await (await fetch('/varieties')).json()).varieties);
  const mine = list.filter((v) => v.name.startsWith(tag));
  results.rows_created = mine.map((v) => [v.variety_id, v.name]);
  // cleanup only the probe rows
  for (const v of mine) await page.evaluate(async (id) => (await fetch('/varieties/' + id, { method: 'DELETE', headers: { 'X-Requested-With': 'RoseProductionGUI' } })).status, v.variety_id);
  const after = await page.evaluate(async () => (await (await fetch('/varieties')).json()).varieties.length);
  results.varieties_after_cleanup = after;
  console.log(JSON.stringify(results, null, 1));
  await browser.close();
})();
