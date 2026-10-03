# Cargo Fit Planner UI refinement — 2026-10-03

This record supersedes only the UI/refinement status in `TODO.md`. The original MVP evidence in `cargo-mvp-2026-10-03.md` remains historical and unchanged.

## Scope delivered

- CSV validation now renders structured row, field, and message details, up to 20 entries with an explicit truncation notice. Invalid submissions preserve the textarea and do not show a stale packing result or export forms.
- Results distinguish source rows from expanded item units and show input, placed, and remaining kilograms to 0.001 kg. Very large finite input totals use bounded scientific notation rather than overflowing to `Infinity`.
- Remaining rows show stable item ID, name, original dimensions, weight, and a plain-language reason. CSV export retains machine-readable reasons and now includes original-item details for placed and unplaced rows.
- Capacity percentages are labeled by their exact denominators and state that they do not predict additional fit. Placed-item buttons connect table rows to SVG box faces, expose pressed state, retain selection across view redraws, and keep the SVG title/description available after redraw.
- Tables remain locally scrollable on small screens; the 375 px browser run verified no document-level horizontal overflow.

## Verification

- Environment: Python 3.14.6, Django 6.1.1, external venv at `C:\Users\DELL\Documents\Codex\2026-10-03\portfolio-cargo-tl\work\cargo-mvp-venv`.
- Canonical repository: [ZephyrianDawnstrider/cargo-fit-planner](https://github.com/ZephyrianDawnstrider/cargo-fit-planner). GitHub rename completed; old `new_and_improved_dcd` page returns HTTP 301 to this URL, and `origin` is configured to the new `.git` URL.
- `PYTHONDONTWRITEBYTECODE=1 python -B manage.py check --settings=dcd_project.settings_demo` — **PASS**.
- `PYTHONDONTWRITEBYTECODE=1 python -B manage.py test optimization.test_mvp_views optimization.test_packing --settings=dcd_project.settings_demo` — **PASS**, 28 tests.
- `node --check scripts/browser-smoke.cjs` — **PASS**.
- Isolated local Django server ran at `127.0.0.1:8762` with `dcd_project.settings_demo`; the direct health GET returned HTTP 200 and the Cargo Fit Planner page title. It uses in-memory SQLite and console logging.
- Headless Chrome through the bundled Playwright runtime, a fresh browser context, and no personal browser profile completed `scripts/browser-smoke.cjs` with exit code 0 and no console errors. The flow verified malformed multi-row validation and source preservation, fixture file selection, 6 input = 5 placed + 1 remaining (`HEAVY-001`, `payload_limit`), exact table/SVG IDs, 15 faces for 5 rendered boxes, first-row selection persisting across a view-angle redraw, accessible SVG labels after redraw, both exports matching the displayed snapshot after editing the textarea without repacking, and a 375 px viewport with `clientWidth=375` and `scrollWidth=375`.
- The browser runner wrote the mobile capture as `cargo-refinement-2026-10-03-desktop.mobile.png`; it was copied without alteration to the concise `cargo-refinement-2026-10-03-mobile.png` deliverable. The smoke script now derives the `-mobile.png` name directly for future runs; no functional browser code changed after the passing run.
- Desktop screenshot: `C:\Users\DELL\Documents\Codex\2026-10-03\portfolio-cargo-tl\outputs\cargo-refinement-2026-10-03-desktop.png`.
- Mobile screenshot: `C:\Users\DELL\Documents\Codex\2026-10-03\portfolio-cargo-tl\outputs\cargo-refinement-2026-10-03-mobile.png`.

The initial 375 px attempt exposed 677 px of document width from the wide result tables. The follow-up CSS constrains the mobile grid/panels while preserving local table scrolling; the passing browser result above reflects that correction. No deployment or live/business database was involved.
