// Run after starting server.mjs. Requires Playwright in the test environment.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1050 }, deviceScaleFactor: 1 });
    const errors = [], requests = []; page.on('pageerror', error => errors.push(error.message)); page.on('request', req => requests.push(req.url()));
    await page.goto(process.env.VIEWER_URL || 'http://127.0.0.1:8765');
    await page.locator('#gates .gate').first().waitFor();
    assert.equal(await page.locator('#score').innerText(), '—');
    assert.equal(await page.locator('#empty-state').isVisible(), true);
    assert.equal(await page.locator('#webgl-error').isVisible(), false);
    const output = process.env.VIEWER_QA_DIR;
    if (output) { await fs.mkdir(output, { recursive: true }); await page.screenshot({ path: path.join(output, 'viewer-pending-desktop.png'), fullPage: true }); }
    const source = JSON.parse(await fs.readFile(path.join(__dirname, '../data/benchmark.json'), 'utf8'));
    source.run = { id: 'QA-FIXTURE', title: '操作検証用メッシュ（ベンチマーク結果ではありません）', model: 'QA only', sourceFiles: [] };
    source.parts = [{ id: 'part-a', name: 'テスト部品 A', color: '#6f929f', vertices: [-50, -50, 0, 50, -50, 0, 50, 50, 0, -50, 50, 0, -50, -50, 160, 50, -50, 160, 50, 50, 160, -50, 50, 160], indices: [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4, 2, 3, 7, 2, 7, 6, 0, 4, 7, 0, 7, 3, 1, 2, 6, 1, 6, 5] }];
    await page.locator('#file-input').setInputFiles({ name: 'qa.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(source)) });
    await page.waitForFunction(() => document.getElementById('part-count').textContent === '1');
    assert.equal(await page.locator('#empty-state').isVisible(), false);
    await page.getByRole('button', { name: 'テスト部品 A', exact: true }).click();
    assert.match(await page.locator('#part-detail').innerText(), /part-a/);
    await page.getByRole('checkbox', { name: 'テスト部品 Aを表示' }).uncheck();
    assert.equal(await page.locator('#visible-count').innerText(), '0 visible');
    await page.locator('#show-all').click(); assert.equal(await page.locator('#visible-count').innerText(), '1 visible');
    await page.locator('#wireframe').check(); await page.locator('#transparent').check(); await page.locator('#section').check();
    await page.locator('#explode').fill('70'); assert.equal(await page.locator('#explode-value').innerText(), '70%');
    await page.getByRole('button', { name: '上', exact: true }).click(); assert.equal(await page.locator('#view-label').innerText(), 'TOP · +Z');
    const evaluation = { schema: source.schema, run: { id: source.run.id }, evaluation: { ...source.evaluation, status: 'self-reported', score: 92, metrics: [{ label: 'テスト指標', value: 123.4, unit: 'N', source: 'QA only' }], issues: ['検証用の未解決事項'] } };
    await page.locator('#file-input').setInputFiles([{ name: 'evaluation.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(evaluation)) }, { name: 'D1.csv', mimeType: 'text/csv', buffer: Buffer.from('time_s,stroke_mm,force_N\n0,0,0\n0.1,25,3500\n0.2,45,6000\n') }]);
    await page.waitForFunction(() => document.getElementById('score').textContent === '92');
    assert.match(await page.locator('#review-status').innerText(), /自己申告/); assert.equal(await page.locator('#readiness').innerText(), '評価待ち');
    await page.locator('#tab-csv').click(); assert.equal(await page.locator('table tbody tr').count(), 3); assert.equal(await page.locator('svg.csv-chart').count(), 1);
    const bad = { ...evaluation, run: { id: 'WRONG-RUN' } };
    await page.locator('#file-input').setInputFiles({ name: 'wrong.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(bad)) });
    await page.getByRole('status').filter({ hasText: '一致しません' }).waitFor(); assert.equal(await page.locator('#score').innerText(), '92');
    // A new assembly must never inherit another run's score or CSV attachments.
    await page.locator('#file-input').setInputFiles({ name: 'fresh.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(source)) });
    await page.waitForFunction(() => document.getElementById('score').textContent === '—'); assert.equal(await page.locator('#csv-count').innerText(), '0');
    await page.locator('#tab-overview').click();
    if (output) await page.screenshot({ path: path.join(output, 'viewer-qa-mesh-desktop.png'), fullPage: true });
    const download = page.waitForEvent('download'); await page.locator('#screenshot').click(); assert.match((await download).suggestedFilename(), /QA-FIXTURE-view\.png/);
    const stl = 'solid qa\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 10 0 0\nvertex 0 10 0\nendloop\nendfacet\nendsolid qa';
    await page.locator('#file-input').setInputFiles({ name: 'direct-stl.stl', mimeType: 'application/octet-stream', buffer: Buffer.from(stl) });
    await page.waitForFunction(() => document.getElementById('run-id').textContent === 'direct-stl'); assert.equal(await page.locator('#part-count').innerText(), '1');
    if (process.env.TEST_CAD_BUNDLE) {
      const cad = JSON.parse(await fs.readFile(process.env.TEST_CAD_BUNDLE, 'utf8'));
      await page.locator('#file-input').setInputFiles(process.env.TEST_CAD_BUNDLE);
      await page.waitForFunction(n => document.getElementById('part-count').textContent === String(n), cad.parts.length);
      assert.equal(await page.locator('#empty-state').isVisible(), false);
      if (output) await page.screenshot({ path: path.join(output, 'viewer-real-freecad-export-qa.png'), fullPage: true });
    }
    await page.reload(); await page.locator('#gates .gate').first().waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    if (output) await page.screenshot({ path: path.join(output, 'viewer-pending-mobile.png'), fullPage: true });
    assert.deepEqual(errors, []); assert(requests.every(url => url.startsWith(process.env.VIEWER_URL || 'http://127.0.0.1:8765') || url.startsWith('blob:')));
    console.log('PASS: pending state, WebGL, mesh/STL import, selection, visibility, display controls, PNG, evaluation attribution, CSV chart, run identity, stale-data reset, mobile layout, no external requests.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
