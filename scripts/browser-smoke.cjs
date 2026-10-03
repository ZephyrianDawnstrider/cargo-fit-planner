const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('playwright');

async function main() {
  const baseUrl = process.env.CARGO_DEMO_URL || 'http://127.0.0.1:8762/';
  const csvPath = path.resolve(process.env.CARGO_DEMO_CSV || 'optimization/fixtures/demo.csv');
  const screenshotPath = process.argv[2];
  if (!screenshotPath) throw new Error('Usage: node scripts/browser-smoke.cjs <absolute-screenshot-path>');
  const chromePath = process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  const browser = await chromium.launch({ headless: true, executablePath: chromePath });
  const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 1050 } });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on('pageerror', error => consoleErrors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  try {
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: 'Load synthetic example' }).click();
    const textarea = page.locator('#cargo-csv');
    if (!(await textarea.inputValue()).includes('BOX,Sample box')) throw new Error('Synthetic-example control did not populate the input');
    const sample = await fs.readFile(csvPath, 'utf8');
    await textarea.fill('');
    await page.locator('#csv-file').setInputFiles(csvPath);
    await page.waitForFunction(expected => document.querySelector('#cargo-csv').value.replace(/\r\n/g, '\n') === expected.replace(/\r\n/g, '\n'), sample);

    const withRemaining = `${sample.trimEnd()}\nHEAVY,Overweight crate,1000,1000,1000,30000,1,true,fixed\n`;
    await textarea.fill(withRemaining);
    await page.getByRole('button', { name: 'Pack cargo' }).click();
    await page.locator('#packing-result').waitFor({ state: 'attached' });
    const result = JSON.parse(await page.locator('#packing-result').textContent());
    const tableIds = await page.locator('.layout + .panel tbody tr td:first-child').allTextContents();
    const remainingIds = await page.locator('.layout .panel tbody tr td:first-child').allTextContents();
    const svgFaceIds = await page.locator('#scene .box-face[data-item-id]').evaluateAll(nodes => [...new Set(nodes.map(node => node.dataset.itemId))]);
    const svgFaceCount = await page.locator('#scene .box-face[data-item-id]').count();
    if (result.totals.input_count !== 6 || result.totals.placed_count !== 5 || result.totals.unplaced_count !== 1) throw new Error(`Unexpected conservation totals: ${JSON.stringify(result.totals)}`);
    if (JSON.stringify([...svgFaceIds].sort()) !== JSON.stringify(result.placed.map(x => x.item_id).sort())) throw new Error('SVG item IDs differ from placed result IDs');
    if (svgFaceCount !== result.placed.length * 3) throw new Error(`Each cuboid must render three visible faces; found ${svgFaceCount}`);
    if (JSON.stringify([...tableIds].sort()) !== JSON.stringify(result.placed.map(x => x.item_id).sort())) throw new Error('Placed item table IDs differ from solver IDs');
    if (!remainingIds.includes('HEAVY-001') || !await page.locator('.layout').getByText('payload_limit').isVisible()) throw new Error('Remaining cargo row or reason is not visible');
    for (const item of result.placed) {
      if (!(item.dx > 0 && item.dy > 0 && item.dz > 0)) throw new Error(`Missing cuboid dimension: ${item.item_id}`);
    }

    const viewBefore = await page.locator('#scene').locator('polygon').first().getAttribute('points');
    await page.getByRole('button', { name: 'Change view angle' }).click();
    const viewAfter = await page.locator('#scene').locator('polygon').first().getAttribute('points');
    if (viewBefore === viewAfter) throw new Error('View-angle control did not change projected geometry');

    await fs.mkdir(path.dirname(path.resolve(screenshotPath)), { recursive: true });
    await page.screenshot({ path: path.resolve(screenshotPath), fullPage: true });

    // An edit after packing must not change either export's submitted-result snapshot.
    await textarea.fill('item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\nEDIT,Changed after pack,100,100,100,1,1,true,fixed\n');
    const [csvDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Export item CSV' }).click(),
    ]);
    const exportedCsv = await fs.readFile(await csvDownload.path(), 'utf8');
    const [jsonDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Export packing JSON' }).click(),
    ]);
    const exportedJson = JSON.parse(await fs.readFile(await jsonDownload.path(), 'utf8'));
    if (!exportedCsv.includes('HEAVY-001') || exportedCsv.includes('EDIT-001')) throw new Error('CSV export did not match the visible packed snapshot');
    if (exportedJson.totals.input_count !== 6 || exportedJson.totals.unplaced_count !== 1 || exportedJson.placed.some(x => x.source_item_id === 'EDIT')) throw new Error('JSON export did not match the visible packed snapshot');
    if (consoleErrors.length) throw new Error(`Browser console errors: ${consoleErrors.join(' | ')}`);

    process.stdout.write(JSON.stringify({
      url: baseUrl,
      uploadedFile: path.basename(csvPath),
      totals: result.totals,
      unplaced: result.unplaced.map(x => ({ item_id: x.item_id, reason: x.reason })),
      tableAndSvgPlacedIds: result.placed.map(x => x.item_id),
      renderedCuboidFaces: svgFaceCount,
      viewControlChangedGeometry: true,
      csvExportMatchesSnapshot: true,
      jsonExportMatchesSnapshot: true,
      consoleErrors,
      screenshot: path.resolve(screenshotPath),
    }, null, 2) + '\n');
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch(error => { process.stderr.write(`${error.stack || error}\n`); process.exitCode = 1; });
