# Cargo Fit Planner manual workflow and weather adapter — 2026-10-04

## Scope and current gate

This source update builds on the stateless Cargo Fit Planner. Manual row editing, Excel TSV paste, exact mm/cm/m conversion, CSV import, existing structured validation, and immutable CSV/JSON export are retained. The entry form now uses full-width labeled cargo cards. The default SVG view fits loaded cargo and states that its floor is cropped; a separate toggle shows the full container footprint without changing packed coordinates. Unchanged coordinates remain in millimetres.

The optional weather request accepts only user-entered latitude/longitude and returns forecast values with requested and model-grid coordinates, model-valid UTC time, retrieval UTC time, source, and model-data attribution. It is a model forecast, not vessel telemetry or navigation advice. Unknown measurements render as “Unknown.” The UI sends no automatic or background request. AIS remains unconfigured and displays no positions; a future feed needs a server-side provider key and review of current service/display terms.

The working tree is on `main` based on `e62b35b21781036b29e7eab9ec49d511bd12c840`; these changes are not committed or deployed in this evidence record. Parent source review and manager visual/release approval are required before main integration or hosting changes. No Render environment or service was changed.

## Provider and runtime limits

The forecast adapter uses the fixed HTTPS Open-Meteo Marine API endpoint, has no upstream credential, proxy, retry, or redirect, limits response bodies to 64 KiB, and uses a five-second socket-inactivity timeout (not a strict wall-clock deadline). Its process-local cache is limited to 32 coordinate keys for ten minutes, with one new upstream request per 60 seconds and 200 upstream attempts per UTC day. Failed upstream attempts count; cache hits do not. These counters reset on restart, are not durable workspace quotas, and would be independent across worker processes. The outer Django admission middleware also bounds POST bodies at 800 KiB and applies a shared four-request burst/refill bucket to packing, export, and weather.

The Render runtime remains an explicit file allowlist and has no database or session middleware. `CARGO_WEATHER_FREE_API_ENABLED` is fail-closed in production settings and is declared as enabled in the Blueprint for the authorized noncommercial educational use. The live service’s environment merge and hosted forecast request are pending release approval. Open-Meteo's API noncommercial-use terms and CC BY 4.0 attribution are separate conditions; see [Marine API](https://open-meteo.com/en/docs/marine-weather-api), [data license](https://open-meteo.com/en/license), and [API terms](https://open-meteo.com/en/terms). No live provider request was made during local tests.

## Verification

Focused local Django suite: 65 tests passed, including manual-view behavior, packer behavior, production allowlist/WSGI flow, POST admission, and 16 mocked tracking-adapter tests. The isolated staged-runtime test verified pack, CSV/JSON exports, and a mocked weather POST. Django reported no system-check issues. Browser verification used a bundled Playwright package with a fresh headless Chrome context after the native Browser runtime was empty; this was an approved unavailable-runtime fallback, not a permission bypass. The weather UI was fulfilled by a local Playwright route fixture; it did not contact Open-Meteo.

The browser smoke checked initial desktop entry/profile preview, manual sample rows, add/remove, mm/cm/m conversion, 1.001 kg and 1.001 m precision, Excel TSV paste, CSV-file import and malformed CSV preservation, exact placed table/SVG item-ID parity, immutable CSV/JSON export after editing without repacking, selected unit count, fit-cargo and full-container camera modes, and a 375 px viewport with no document-level overflow. The cargo-fit SVG faces measured approximately 329 × 300 px in the tested fixture. Browser console errors: none.

Fresh screenshots are in the task output folder:

- Initial first fold: `cargo-fit-planner-release-review-2026-10-04-initial.png`
- Packed desktop: `cargo-fit-planner-release-review-2026-10-04-desktop.png`
- Packed mobile: `cargo-fit-planner-release-review-2026-10-04-mobile.png`

The separate mobile coordinate table intentionally scrolls horizontally and has a visible instruction. This capture does not prove hosted behavior, an actual upstream forecast, cold-start/restart behavior, account billing controls, or a deployment.
