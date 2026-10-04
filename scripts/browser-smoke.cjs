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

    await page.locator('#container-selector').selectOption('custom_dry');
    await page.locator('#custom-name').fill('Measured sample box');
    await page.locator('#custom-inside-length').fill('5000');
    await page.locator('#custom-inside-width').fill('2200');
    await page.locator('#custom-inside-height').fill('2300');
    await page.locator('#custom-door-width').fill('2100');
    await page.locator('#custom-door-height').fill('2200');
    await page.locator('#custom-payload').fill('24000');
    await page.locator('#custom-source-kind').selectOption('equipment_plate');
    await page.locator('#custom-source-reference').fill('Plate A-19');
    await page.locator('#dimension-unit').selectOption('m');
    if (await page.locator('#custom-inside-length').inputValue() !== '5' || await rows.nth(0).locator('[data-field="length_mm"]').inputValue() !== '0.6') throw new Error('Custom dimensions did not follow the shared unit conversion');
    await page.getByRole('button', { name: 'Load sample cargo' }).click();
    if (await page.locator('#dimension-unit').inputValue() !== 'mm' || await page.locator('#custom-inside-length').inputValue() !== '5000') throw new Error('Loading sample cargo changed the custom profile dimensions');
    await page.locator('#container-selector').selectOption('40hc');

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
    await preciseRow.locator('[data-field="load_unit_type"]').selectOption('drum_roll');
    await preciseRow.locator('[data-field="floor_only"]').check();
    await unit.selectOption('mm');

    await page.getByRole('button', { name: 'Paste Excel rows' }).click();
    const tsv = 'PASTE\tExcel pallet\t800\t600\t500\t25.125\t1\tfalse\tfixed\tpalletized\ttrue\tfalse\t\t\t';
    await page.locator('#excel-paste').fill(tsv);
    await page.getByRole('button', { name: 'Add pasted rows' }).click();
    if (await rows.count() !== 4 || await rows.nth(3).locator('[data-field="name"]').inputValue() !== 'Excel pallet' || await rows.nth(3).locator('[data-field="floor_only"]').isChecked() !== true || await rows.nth(3).locator('[data-field="load_unit_type"]').inputValue() !== 'palletized') throw new Error('Extended Excel TSV paste with trailing empty metadata cells failed');
    const legacyTsv = 'LEGACY\tLegacy carton\t100\t100\t100\t1\t1\ttrue\tfixed';
    await page.locator('#excel-paste').fill(legacyTsv);
    await page.getByRole('button', { name: 'Add pasted rows' }).click();
    if (await rows.count() !== 5 || await rows.nth(4).locator('[data-field="load_unit_type"]').inputValue() !== 'carton_crate' || await rows.nth(4).locator('[data-field="is_dg"]').isChecked()) throw new Error('Legacy nine-column Excel paste did not receive safe optional defaults');
    await page.getByRole('button', { name: 'Add item row' }).click();
    const dgRow = rows.nth(5);
    await dgRow.locator('[data-field="item_id"]').fill('DG');
    await dgRow.locator('[data-field="name"]').fill('Paint drum');
    await dgRow.locator('[data-field="length_mm"]').fill('100');
    await dgRow.locator('[data-field="width_mm"]').fill('100');
    await dgRow.locator('[data-field="height_mm"]').fill('100');
    await dgRow.locator('[data-field="weight_kg"]').fill('20');
    await dgRow.locator('[data-field="stackable"]').uncheck();
    await dgRow.locator('[data-field="floor_only"]').check();
    await dgRow.locator('[data-field="is_dg"]').check();
    await dgRow.locator('[data-field="load_unit_type"]').selectOption('drum_roll');
    await dgRow.locator('[data-field="un_number"]').fill('UN1263');
    await dgRow.locator('[data-field="imdg_class"]').fill('3');
    await dgRow.locator('[data-field="packing_group"]').fill('II');
    await page.locator('summary').filter({ hasText: 'Shipment and document references' }).click();
    await page.locator('[name="shipment_reference"]').fill('=SHIP-42');
    await page.locator('[name="booking_reference"]').fill('BOOK-17');
    await page.locator('[name="bill_of_lading"]').fill('BOL-5');
    await page.getByRole('button', { name: 'Pack cargo' }).click();
    await page.locator('#packing-result').waitFor({ state: 'attached' });
    const result = JSON.parse(await page.locator('#packing-result').textContent());
    if (result.container.id !== '40hc' || result.totals.input_count !== 9 || result.totals.unplaced_count + result.totals.placed_count !== 9 || result.readiness !== 'manual_compliance_hold' || result.totals.manual_compliance_hold_count !== 1) throw new Error(`Unexpected manual packing result: ${JSON.stringify({container:result.container,totals:result.totals,readiness:result.readiness})}`);
    const resultPanels = await page.evaluate(() => { const ws=document.querySelector('.workspace').getBoundingClientRect(),remaining=document.querySelector('.remaining-panel').getBoundingClientRect(),weather=document.querySelector('.weather-panel').getBoundingClientRect();return {workspaceBottom:ws.bottom,remainingTop:remaining.top,remainingWidth:remaining.width,weatherTop:weather.top}; });
    if (resultPanels.remainingTop < resultPanels.workspaceBottom || resultPanels.remainingTop > resultPanels.weatherTop || resultPanels.remainingWidth < 700) throw new Error(`Remaining cargo is not full-width between packing and optional weather: ${JSON.stringify(resultPanels)}`);
    const heldDg = result.unplaced.find(item => item.source_item_id === 'DG');
    if (!heldDg || heldDg.reason !== 'manual_compliance_hold' || heldDg.un_number !== 'UN1263' || heldDg.imdg_class !== '3' || heldDg.packing_group !== 'II' || heldDg.load_unit_type !== 'drum_roll') throw new Error('Dangerous-goods metadata was not preserved in the manual hold');
    const tableIds = await page.locator('.placed-panel tbody tr[data-item-id]').evaluateAll(nodes => nodes.map(node => node.dataset.itemId).sort());
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
    if (!submitted.includes('800,600,500,25.125') || !submitted.includes('PASTE,Excel pallet,800,600,500,25.125') || !submitted.includes('PRECISE,Precision case,1001,100,100,1.001') || !submitted.includes('DG,Paint drum,100,100,100,20.000,1,false,fixed,drum_roll,true,true,UN1263,3,II')) throw new Error('Manual inputs or DG metadata were not normalized into the submitted CSV');

    await page.screenshot({ path: path.resolve(screenshotPath), fullPage: true });
    const mobileScreenshot = path.resolve(screenshotPath).replace(/-desktop(?=\.[^.]+$)/, '-mobile');
    await page.setViewportSize({ width: 375, height: 812 });
    const mobile = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    if (mobile.scroll > mobile.client) { const offenders=await page.evaluate(()=>{const els=[...document.querySelectorAll('body > *, main > *, main section, main details, main .panel')].map(el=>({tag:el.tagName,id:el.id,cls:String(el.className?.baseVal??el.className??'').slice(0,70),left:Math.round(el.getBoundingClientRect().left),right:Math.round(el.getBoundingClientRect().right),width:Math.round(el.getBoundingClientRect().width),scroll:el.scrollWidth,client:el.clientWidth})).filter(el=>el.right>document.documentElement.clientWidth+1||el.scroll>el.client+1);const panel=document.querySelector('.entry-panel');const children=[...panel.querySelectorAll('*')].map(el=>({tag:el.tagName,id:el.id,cls:String(el.className?.baseVal??el.className??'').slice(0,45),left:Math.round(el.getBoundingClientRect().left),right:Math.round(el.getBoundingClientRect().right),width:Math.round(el.getBoundingClientRect().width)})).filter(el=>el.right>panel.getBoundingClientRect().right+1).slice(0,10);return{els,children}});throw new Error(`Mobile layout overflow: ${JSON.stringify({mobile,...offenders})}`); }
    const mobileFields = ['item_id','name','length_mm','width_mm','height_mm','weight_kg','quantity','stackable','orientation','load_unit_type','floor_only','is_dg','un_number','imdg_class','packing_group'];
    for (const field of mobileFields) if (!await page.locator(`#cargo-rows tr`).first().locator(`[data-field="${field}"]`).isVisible()) throw new Error(`Mobile cargo card hides ${field}`);
    const remainingSummary = await page.locator('.remaining-mobile-card').innerText();
    if (!remainingSummary.includes('DG-001') || !remainingSummary.includes('UN1263') || !remainingSummary.includes('manual dangerous-goods compliance hold')) throw new Error(`Mobile remaining-cargo card omits actionable reason or DG fields: ${remainingSummary}`);
    await page.screenshot({ path: mobileScreenshot, fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1050 });

    await rows.nth(0).locator('[data-field="name"]').fill('Edited after pack');
    await page.locator('#container-selector').selectOption('20std');
    await page.locator('summary').filter({ hasText: 'Shipment and document references' }).click();
    await page.getByLabel('Shipment reference').fill('CHANGED-AFTER-PACK');
    await page.getByRole('button', { name: 'Add item row' }).click();
    const blankWeight = rows.nth(6);
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
    if (!exportedCsv.includes('PASTE-001') || exportedCsv.includes('Edited after pack') || !exportedCsv.includes("'=SHIP-42") || !exportedCsv.includes('40hc,') || exportedCsv.includes('CHANGED-AFTER-PACK')) throw new Error('CSV export differs from visible-result snapshot');
    if (exportedJson.totals.input_count !== 9 || exportedJson.placed.some(item => item.name === 'Edited after pack') || exportedJson.container.id !== '40hc' || exportedJson.shipment.shipment_reference !== '=SHIP-42' || exportedJson.readiness !== 'manual_compliance_hold') throw new Error('JSON export differs from visible-result snapshot');

    await page.locator('#csv-file').setInputFiles(csvPath);
    const fixtureCsv = await fs.readFile(csvPath, 'utf8');
    await page.waitForFunction(expected => document.querySelector('#csv-editor').value.replace(/\r\n/g, '\n') === expected.replace(/\r\n/g, '\n'), fixtureCsv);
    await page.getByRole('button', { name: 'Pack cargo' }).click();
    await page.locator('#packing-result').waitFor({ state: 'attached' });
    const csvImportResult = JSON.parse(await page.locator('#packing-result').textContent());
    if (csvImportResult.totals.input_count !== 5) throw new Error('CSV import workflow did not use imported file');

    const extendedCsv = 'item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation,load_unit_type,floor_only,is_dg,un_number,imdg_class,packing_group\nEXT,Extended pallet,500,400,300,4.125,1,true,fixed,palletized,true,false,,,\n';
    await page.locator('#csv-tools').evaluate(element => { element.open = true; });
    await page.locator('#csv-editor').fill(extendedCsv);
    await page.getByRole('button', { name: 'Load CSV into item rows' }).click();
    if (await rows.count() !== 1 || await rows.first().locator('[data-field="load_unit_type"]').inputValue() !== 'palletized' || !(await rows.first().locator('[data-field="floor_only"]').isChecked()) || await rows.first().locator('[data-field="is_dg"]').isChecked()) throw new Error('Extended CSV import did not preserve load-unit and floor/DG metadata');
    const invalid = 'item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\nBAD1,First,abc,100,100,nope,1,maybe,fixed\nBAD2,Second,100,0,100,1,1,true,diagonal\n';
    const preservedRowIds = await rows.evaluateAll(nodes => nodes.map(node => node.querySelector('[data-field="item_id"]').value));
    await page.locator('#csv-tools').evaluate(element => { element.open = true; });
    await page.locator('#csv-editor').fill(invalid);
    await page.getByRole('button', { name: 'Load CSV into item rows' }).click();
    if (!(await page.locator('#csv-mode-feedback').innerText()).includes('invalid stackable')) throw new Error('Malformed CSV was silently normalized into manual fields');
    if (JSON.stringify(await rows.evaluateAll(nodes => nodes.map(node => node.querySelector('[data-field="item_id"]').value))) !== JSON.stringify(preservedRowIds)) throw new Error('Malformed CSV import replaced the existing manual rows');
    await page.locator('#csv-tools').evaluate(element => { element.open = true; });
    await page.locator('#csv-editor').fill(invalid);
    await page.getByRole('button', { name: 'Pack cargo' }).click();
    const alert = page.getByRole('alert');
    await alert.waitFor({ state: 'visible' });
    const validationText = await alert.innerText();
    if (!validationText.includes('Row 2 · length_mm') || !validationText.includes('Row 3 · width_mm')) throw new Error(`CSV row errors missing: ${validationText}`);
    if (await page.locator('#packing-result').count() || await page.locator('.export-form').count()) throw new Error('Invalid CSV left stale result or export visible');
    if (await page.locator('#csv-editor').inputValue() !== invalid) throw new Error('Invalid CSV was not preserved');
    await page.getByRole('button', { name: 'Load sample cargo' }).click();
    await page.locator('#container-selector').selectOption('custom_dry');
    await page.locator('#custom-name').fill('Measured private box');
    await page.locator('#custom-inside-length').fill('5000');
    await page.locator('#custom-inside-width').fill('2200');
    await page.locator('#custom-inside-height').fill('2300');
    await page.locator('#custom-door-width').fill('2100');
    await page.locator('#custom-door-height').fill('2200');
    await page.locator('#custom-payload').fill('24000');
    await page.locator('#custom-source-kind').selectOption('user_measurement');
    await page.locator('#custom-source-reference').fill('Measured on site');
    await page.getByRole('button', { name: 'Pack cargo' }).click();
    const customResult = JSON.parse(await page.locator('#packing-result').textContent());
    if (customResult.container.id !== 'custom_dry' || customResult.container.status !== 'unverified_measured' || customResult.container.dimensions_source.reference !== 'Measured on site') throw new Error('Custom dry profile provenance was not retained in the result');
    await page.locator('#container-selector').selectOption('40std');
    const [customJsonDownload] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Export packing JSON' }).click()]);
    const customJson = JSON.parse(await fs.readFile(await customJsonDownload.path(), 'utf8'));
    if (customJson.container.id !== 'custom_dry' || customJson.container.dimensions_source.kind !== 'user_measurement' || customJson.container.dimensions_source.reference !== 'Measured on site') throw new Error('Custom profile export changed after the visible profile selector was edited');
    await page.locator('#container-selector').selectOption('custom_dry');
    await page.locator('summary').filter({ hasText: 'Browse other equipment families' }).click();
    const customCatalogueScreenshot = path.resolve(screenshotPath).replace(/-desktop(?=\.[^.]+$)/, '-custom-catalogue');
    await page.screenshot({ path: customCatalogueScreenshot, fullPage: true });
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
      named40hcProfile: true,
      customProfileUnitAndSnapshot: true,
      extendedTsvAndLegacyTsv: true,
      extendedCsvImportPreservedMetadata: true,
      dangerousGoodsManualHold: true,
      shipmentAndContainerExportsImmutable: true,
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
      screenshots: [initialScreenshot, path.resolve(screenshotPath), mobileScreenshot, customCatalogueScreenshot],
      consoleErrors,
    }, null, 2) + '\n');
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch(error => { process.stderr.write(`${error.stack || error}\n`); process.exitCode = 1; });
