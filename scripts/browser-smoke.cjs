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
    const textarea = page.locator('#cargo-csv');
    const malformed = 'item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation\nBAD1,First,abc,100,100,nope,1,true,fixed\nBAD2,Second,100,0,100,1,1,true,diagonal\n';
    await textarea.fill(malformed);
    await page.getByRole('button', { name: 'Pack cargo' }).click();
    const validationAlert = page.getByRole('alert');
    await validationAlert.waitFor({ state: 'visible' });
    const validationText = await validationAlert.innerText();
    if (!validationText.includes('Row 2 · length_mm') || !validationText.includes('Row 3 · width_mm')) throw new Error(`Structured row errors were not shown: ${validationText}`);
    if (await page.locator('#packing-result').count() || await page.locator('.export-form').count()) throw new Error('Invalid submission left a stale result or export form visible');
    if (await textarea.inputValue() !== malformed) throw new Error('Malformed CSV was not preserved for correction');

    await page.getByRole('button', { name: 'Load synthetic example' }).click();
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
    if (!remainingIds.includes('HEAVY-001') || !await page.locator('.layout').getByText('Would exceed payload limit').isVisible()) throw new Error('Remaining cargo row or human-readable reason is not visible');
    for (const item of result.placed) {
      if (!(item.dx > 0 && item.dy > 0 && item.dz > 0)) throw new Error(`Missing cuboid dimension: ${item.item_id}`);
    }

    const viewBefore = await page.locator('#scene').locator('polygon').first().getAttribute('points');
    await page.getByRole('button', { name: 'Change view angle' }).click();
    const viewAfter = await page.locator('#scene').locator('polygon').first().getAttribute('points');
    if (viewBefore === viewAfter) throw new Error('View-angle control did not change projected geometry');
    const sceneLabels = await page.locator('#scene').getAttribute('aria-labelledby');
    if (!sceneLabels || !await page.locator('#scene').evaluate((scene, ids) => ids.split(/\s+/).every(id => Boolean(scene.querySelector(`#${id}`))), sceneLabels)) throw new Error('Accessible SVG title/description missing after redraw');
    const firstPlacedId = result.placed[0].item_id;
    const firstItemButton = page.getByRole('button', { name: `Highlight placed item ${firstPlacedId}` });
    await firstItemButton.click();
    if (await page.locator(`#scene .box-face[data-item-id="${firstPlacedId}"].is-highlighted`).count() !== 3) throw new Error('Selecting the first item did not highlight its three visible faces');
    await page.getByRole('button', { name: 'Change view angle' }).click();
    if (await page.locator(`#scene .box-face[data-item-id="${firstPlacedId}"].is-highlighted`).count() !== 3) throw new Error('Selection was lost after the view angle changed');
    if (await firstItemButton.getAttribute('aria-pressed') !== 'true') throw new Error('Selected item state is not exposed to assistive technology');

    await fs.mkdir(path.dirname(path.resolve(screenshotPath)), { recursive: true });
    await page.screenshot({ path: path.resolve(screenshotPath), fullPage: true });
    const mobileBasename = path.basename(screenshotPath).replace(/-desktop(?=\.[^.]+$)/, '-mobile');
    const mobileScreenshot = path.join(path.dirname(path.resolve(screenshotPath)), mobileBasename);
    await page.setViewportSize({ width: 375, height: 812 });
    await page.screenshot({ path: mobileScreenshot, fullPage: true });
    const mobileLayout = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    if (mobileLayout.scroll > mobileLayout.client) {
      const overflow = await page.evaluate(() => [...document.querySelectorAll('body *')].map(el => {
        const rect = el.getBoundingClientRect();
        return { tag: el.tagName, id: el.id, className: typeof el.className === 'string' ? el.className : el.getAttribute('class'), left: Math.round(rect.left), right: Math.round(rect.right), width: Math.round(rect.width), scrollWidth: el.scrollWidth, clientWidth: el.clientWidth, ancestors: [...(function*(){let parent=el.parentElement; while(parent && parent !== document.body){yield parent; parent=parent.parentElement;}})()].slice(0,4).map(parent => ({tag: parent.tagName, className: parent.getAttribute('class'), width: Math.round(parent.getBoundingClientRect().width), scrollWidth: parent.scrollWidth, clientWidth: parent.clientWidth, overflowX: getComputedStyle(parent).overflowX})) };
      }).filter(el => el.right > innerWidth + 1 || el.scrollWidth > el.clientWidth + 1).sort((a, b) => b.right - a.right).slice(0, 12));
      throw new Error(`Mobile page has horizontal overflow: ${JSON.stringify({ ...mobileLayout, overflow })}`);
    }
    await page.setViewportSize({ width: 1440, height: 1050 });

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
      structuredErrorsPreservedAndNoStaleResult: true,
      selectedFirstItemFacesPersistAfterRedraw: true,
      accessibleSvgLabelsPersistAfterRedraw: true,
      mobileDocumentWidth: mobileLayout,
      csvExportMatchesSnapshot: true,
      jsonExportMatchesSnapshot: true,
      consoleErrors,
      screenshot: path.resolve(screenshotPath),
      mobileScreenshot,
    }, null, 2) + '\n');
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch(error => { process.stderr.write(`${error.stack || error}\n`); process.exitCode = 1; });
