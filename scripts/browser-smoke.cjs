const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'playwright');

async function main() {
  const baseUrl = process.env.CARGO_DEMO_URL || 'http://127.0.0.1:8762/';
  const csvPath = path.resolve(process.env.CARGO_DEMO_CSV || 'optimization/fixtures/demo.csv');
  const screenshotPath = process.argv[2];
  if (!screenshotPath) throw new Error('Usage: node scripts/browser-smoke.cjs <absolute-desktop-screenshot-path>');
  const chromePath = process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  const browser = await chromium.launch({ headless: true, executablePath: chromePath });
  const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 1050 } });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on('pageerror', error => consoleErrors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  try {
    const home = await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    if (!home || home.status() !== 200) throw new Error(`Home page returned ${home && home.status()}`);
    await fs.mkdir(path.dirname(path.resolve(screenshotPath)), { recursive: true });
    const initialScreenshot = path.resolve(screenshotPath).replace(/-desktop(?=\.[^.]+$)/, '-initial');
    await page.screenshot({ path: initialScreenshot });
    const firstFold = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth, entry: !!document.querySelector('.entry-panel'), preview: !!document.querySelector('.empty-preview') }));
    if (!firstFold.entry || !firstFold.preview || firstFold.scroll > firstFold.width) throw new Error(`Initial first fold missing entry/preview or overflows: ${JSON.stringify(firstFold)}`);
    const forecastFixture = {status:'forecast',requested_coordinates:{latitude:12.5,longitude:72.5},forecast_grid_coordinates:{latitude:12.25,longitude:72.75},valid_at:'2026-10-04T12:00:00Z',retrieved_at:'2026-10-04T11:00:00Z',wave_height_m:null,wave_period_s:4.2,wave_direction_deg:180,source:{name:'Open-Meteo test fixture',url:'https://open-meteo.com/en/docs/marine-weather-api',model:'Best Match (fixture)',model_attribution:'Fixture attribution',model_attribution_url:'https://open-meteo.com/en/docs/marine-weather-api#data-sources'},cached:false,notice:'Mocked browser fixture; no provider request was sent.'};
    await page.route('**/weather/', route => route.fulfill({ status:200,contentType:'application/json',body:JSON.stringify(forecastFixture) }));
    await page.locator('[name="latitude"]').fill('12.5');
    await page.locator('[name="longitude"]').fill('72.5');
    await page.getByRole('button', { name: 'Get forecast' }).click();
    await page.locator('#weather-result').waitFor({ state:'visible' });
    if (await page.locator('#weather-height').innerText() !== 'Unknown' || !(await page.locator('#weather-feedback').innerText()).includes('Mocked browser fixture')) throw new Error('Weather UI did not preserve unknown values or fixture notice');
    await page.getByRole('button', { name: 'Load sample cargo' }).click();
    const rows = page.locator('#cargo-rows tr');
    if (await rows.count() !== 2 || await rows.nth(0).locator('[data-field="item_id"]').inputValue() !== 'BOX') throw new Error('Sample did not load into editable rows');

    const unit = page.locator('#dimension-unit');
    const length = rows.nth(0).locator('[data-field="length_mm"]');
    await unit.selectOption('cm');
    if (await length.inputValue() !== '60') throw new Error('mm to cm conversion failed');
    await unit.selectOption('m');
    if (await length.inputValue() !== '0.6') throw new Error('cm to m conversion failed');
    await unit.selectOption('mm');
    if (await length.inputValue() !== '600') throw new Error('m to mm conversion failed');

    await page.getByRole('button', { name: 'Add item row' }).click();
    if (await rows.count() !== 3) throw new Error('Add-row control failed');
    await rows.nth(2).getByRole('button', { name: 'Remove cargo row' }).click();
    if (await rows.count() !== 2) throw new Error('Remove-row control failed');

    await unit.selectOption('m');
    await page.getByRole('button', { name: 'Add item row' }).click();
    const preciseRow = rows.nth(2);
    await preciseRow.locator('[data-field="item_id"]').fill('PRECISE');
    await preciseRow.locator('[data-field="name"]').fill('Precision case');
    await preciseRow.locator('[data-field="length_mm"]').fill('1.001');
    await preciseRow.locator('[data-field="width_mm"]').fill('0.1');
    await preciseRow.locator('[data-field="height_mm"]').fill('0.1');
    await preciseRow.locator('[data-field="weight_kg"]').fill('1.001');
    await preciseRow.locator('[data-field="orientation"]').selectOption('fixed');
    await unit.selectOption('mm');

    await page.getByRole('button', { name: 'Paste Excel rows' }).click();
    const tsv = 'PASTE\tExcel pallet\t800\t600\t500\t25.125\t1\tfalse\tfixed';
    await page.locator('#excel-paste').fill(tsv);
    await page.getByRole('button', { name: 'Add pasted rows' }).click();
    if (await rows.count() !== 4 || await rows.nth(3).locator('[data-field="name"]').inputValue() !== 'Excel pallet') throw new Error('Excel TSV paste failed');
    await page.getByRole('button', { name: 'Pack cargo' }).click();
    await page.locator('#packing-result').waitFor({ state: 'attached' });
    const result = JSON.parse(await page.locator('#packing-result').textContent());
    if (result.totals.input_count !== 7 || result.totals.unplaced_count + result.totals.placed_count !== 7) throw new Error(`Unexpected manual packing totals: ${JSON.stringify(result.totals)}`);
    const tableIds = await page.locator('.layout + .panel tbody tr[data-item-id]').evaluateAll(nodes => nodes.map(node => node.dataset.itemId).sort());
    const svgIds = await page.locator('#scene .box-face[data-item-id]').evaluateAll(nodes => [...new Set(nodes.map(node => node.dataset.itemId))].sort());
    if (JSON.stringify(tableIds) !== JSON.stringify(result.placed.map(item => item.item_id).sort()) || JSON.stringify(svgIds) !== JSON.stringify(tableIds)) throw new Error('Placed table and SVG item IDs differ');
    if (!(await page.locator('#scene-mode-note').innerText()).includes('Fit cargo view')) throw new Error('Cargo-fit view is not the default');
    const fitBounds = await page.locator('#scene').evaluate(scene => { const boxes=[...scene.querySelectorAll('.box-face[data-item-id]')].map(node=>node.getBBox());return {width:Math.max(...boxes.map(box=>box.x+box.width))-Math.min(...boxes.map(box=>box.x)),height:Math.max(...boxes.map(box=>box.y+box.height))-Math.min(...boxes.map(box=>box.y))}; });
    if (fitBounds.width < 100 || fitBounds.height < 60) throw new Error(`Cargo-fit boxes are not legible: ${JSON.stringify(fitBounds)}`);
    await page.getByRole('button', { name: 'Show full container' }).click();
    if (!(await page.locator('#scene-mode-note').innerText()).includes('Full container view')) throw new Error('Full-container toggle did not disclose scale mode');
    await page.getByRole('button', { name: 'Fit loaded cargo' }).click();
    if (!(await page.locator('#scene-mode-note').innerText()).includes('Fit cargo view')) throw new Error('Fit-cargo toggle did not restore default view');
    const submitted = await page.locator('#cargo-csv').inputValue();
    if (!submitted.includes('800,600,500,25.125') || !submitted.includes('PASTE,Excel pallet') || !submitted.includes('PRECISE,Precision case,1001,100,100,1.001')) throw new Error('Manual inputs were not normalized into the submitted CSV');

    await page.screenshot({ path: path.resolve(screenshotPath), fullPage: true });
    const mobileScreenshot = path.resolve(screenshotPath).replace(/-desktop(?=\.[^.]+$)/, '-mobile');
    await page.setViewportSize({ width: 375, height: 812 });
    const mobile = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    if (mobile.scroll > mobile.client) throw new Error(`Mobile layout overflow: ${JSON.stringify(mobile)}`);
    const mobileFields = ['item_id','name','length_mm','width_mm','height_mm','weight_kg','quantity','stackable','orientation'];
    for (const field of mobileFields) if (!await page.locator(`#cargo-rows tr`).first().locator(`[data-field="${field}"]`).isVisible()) throw new Error(`Mobile cargo card hides ${field}`);
    await page.screenshot({ path: mobileScreenshot, fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1050 });

    await rows.nth(0).locator('[data-field="name"]').fill('Edited after pack');
    await page.getByRole('button', { name: 'Add item row' }).click();
    const blankWeight = rows.nth(4);
    await blankWeight.locator('[data-field="item_id"]').fill('NO_WEIGHT');
    await blankWeight.locator('[data-field="name"]').fill('Missing weight');
    await blankWeight.locator('[data-field="length_mm"]').fill('100');
    await blankWeight.locator('[data-field="width_mm"]').fill('100');
    await blankWeight.locator('[data-field="height_mm"]').fill('100');
    await page.getByRole('button', { name: 'Pack cargo' }).click();
    if (!(await page.locator('#manual-feedback').innerText()).includes('weight in kilograms is required')) throw new Error('Missing manual weight was not rejected');
    await blankWeight.getByRole('button', { name: 'Remove cargo row' }).click();
    const [csvDownload] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Export item CSV' }).click()]);
    const exportedCsv = await fs.readFile(await csvDownload.path(), 'utf8');
    const [jsonDownload] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Export packing JSON' }).click()]);
    const exportedJson = JSON.parse(await fs.readFile(await jsonDownload.path(), 'utf8'));
    if (!exportedCsv.includes('PASTE-001') || exportedCsv.includes('Edited after pack')) throw new Error('CSV export differs from visible-result snapshot');
    if (exportedJson.totals.input_count !== 7 || exportedJson.placed.some(item => item.name === 'Edited after pack')) throw new Error('JSON export differs from visible-result snapshot');

    await page.locator('#csv-file').setInputFiles(csvPath);
    const fixtureCsv = await fs.readFile(csvPath, 'utf8');
    await page.waitForFunction(expected => document.querySelector('#csv-editor').value.replace(/\r\n/g, '\n') === expected.replace(/\r\n/g, '\n'), fixtureCsv);
    await page.getByRole('button', { name: 'Pack cargo' }).click();
    await page.locator('#packing-result').waitFor({ state: 'attached' });
    const csvImportResult = JSON.parse(await page.locator('#packing-result').textContent());
    if (csvImportResult.totals.input_count !== 5) throw new Error('CSV import workflow did not use imported file');

    const invalid = 'item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\nBAD1,First,abc,100,100,nope,1,maybe,fixed\nBAD2,Second,100,0,100,1,1,true,diagonal\n';
    await page.locator('#csv-tools').evaluate(element => { element.open = true; });
    await page.getByRole('button', { name: 'Load CSV into item rows' }).click();
    await page.locator('#csv-editor').fill(invalid);
    await page.getByRole('button', { name: 'Load CSV into item rows' }).click();
    if (!(await page.locator('#csv-mode-feedback').innerText()).includes('unsupported stackable')) throw new Error('Malformed CSV was silently normalized into manual fields');
    await page.locator('#csv-tools').evaluate(element => { element.open = true; });
    await page.locator('#csv-editor').fill(invalid);
    await page.getByRole('button', { name: 'Pack cargo' }).click();
    const alert = page.getByRole('alert');
    await alert.waitFor({ state: 'visible' });
    const validationText = await alert.innerText();
    if (!validationText.includes('Row 2 · length_mm') || !validationText.includes('Row 3 · width_mm')) throw new Error(`CSV row errors missing: ${validationText}`);
    if (await page.locator('#packing-result').count() || await page.locator('.export-form').count()) throw new Error('Invalid CSV left stale result or export visible');
    if (await page.locator('#csv-editor').inputValue() !== invalid) throw new Error('Invalid CSV was not preserved');
    if (consoleErrors.length) throw new Error(`Browser console errors: ${consoleErrors.join(' | ')}`);

    process.stdout.write(JSON.stringify({
      url: baseUrl,
      initialFirstFold: firstFold,
      weatherUiMocked: true,
      manualSampleRows: 2,
      dimensionConversions: ['mm→cm', 'cm→m', 'm→mm'],
      addRemoveRow: true,
      excelTsvPaste: true,
      manualTotals: result.totals,
      exactDecimalInputsAccepted: true,
      missingWeightRejected: true,
      tableSvgIdsMatch: true,
      cargoFitBounds: fitBounds,
      fullContainerToggle: true,
      canonicalSubmittedCsv: true,
      csvFileImportUnits: csvImportResult.totals.input_count,
      structuredCsvErrorsRows: [2, 3],
      invalidCsvPreservedWithoutStaleResult: true,
      exportsMatchImmutableSnapshot: true,
      mobileViewport: mobile,
      mobileCargoFieldsVisible: true,
      screenshots: [initialScreenshot, path.resolve(screenshotPath), mobileScreenshot],
      consoleErrors,
    }, null, 2) + '\n');
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch(error => { process.stderr.write(`${error.stack || error}\n`); process.exitCode = 1; });
