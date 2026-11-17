# Cargo Fit Planner

This project includes a database-free deterministic cargo-planning workflow. Enter items in the editable row grid, paste tab-separated columns copied from Excel, or use the advanced CSV import/editor. Select one of three published dry-container examples or enter measurements and provenance for an explicitly unverified closed dry freight container. The heuristic expands quantities to stable item IDs and shows placements, remaining cargo, an isometric view, and CSV/JSON exports. Dangerous goods are withheld for manual review; a geometry result is not operational approval, and the supported profile examples are not a universal equipment catalogue or optimization claim.

## Current interactive workflow — 2026-10-04

The main entry path is manual row editing with add/remove controls and an explicit Excel TSV paste panel. Select mm, cm, or m for dimension entry; values convert exactly to whole millimetres, and unsupported precision is reported instead of rounded. Weights remain in kilograms at 0.001 kg precision. Sample cargo loads directly into editable rows. The CSV template, file import, and advanced CSV editor remain available; CSV can be loaded into manual rows only after its structure and flags are safe to represent. Exports remain tied to the exact submitted manifest, so later edits require repacking. The default 3D camera fits the loaded cargo and labels its cropped-floor view; a control shows the complete container without changing placements or coordinates.

Repository: [ZephyrianDawnstrider/cargo-fit-planner](https://github.com/ZephyrianDawnstrider/cargo-fit-planner).

## Run locally

Use Python 3.12 or newer. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-demo.txt
.\run_demo.ps1
```

Open `http://127.0.0.1:8762/`, select **Load sample cargo**, then **Pack cargo**. Download the CSV template from the page. Demo settings replace the legacy SQL Server databases and routers with in-memory SQLite, disable file logging, and do not read or write the tracked runtime database. Use only synthetic data in this local demonstration. The original database-backed route remains at `/` with the default settings; the isolated demo settings use a separate URL map and do not enable that environment.

The packing result is a deterministic feasibility heuristic. It handles rectangular dimensions, doorway and container fit, overlap, example payload limits, fixed or yaw orientation, and separate floor-only and support-above constraints. `stackable=true` means the cargo unit may support cargo above; `floor_only=true` requires its placement to start at floor level. Palletized dimensions and weight are gross outer-load-unit values including the pallet. Upright drum/roll cargo is only an axis-aligned bounding box; rolling, tipping, lashing, load strength, floor point loads, loading sequence/access, axle limits, and special handling are not modeled. Review the actual equipment plate and carrier documentation before operational use. Displayed weight and volume percentages are simple ratios against profile payload and internal volume; they do not predict fit.

CSV input is limited to 256 KiB in the demo route, 100 source rows, and 100 expanded units. Dimensions must convert to whole millimetres (1 mm resolution); weight accepts 0.001 kg increments. The original nine columns remain required. Optional columns are `load_unit_type` (`carton_crate`, `palletized`, `drum_roll`), `floor_only`, `is_dg`, `un_number`, `imdg_class`, and `packing_group`. Present boolean columns require explicit values. Dangerous-goods rows are exported with their metadata and a manual-compliance hold; no segregation, stowage, acceptance, or transport approval is provided. The named profiles are example steel-container specifications from this [Maersk equipment PDF](https://www.maersk.com.cn/~/media_sc9/maersk/local-information/files/africa/madagascar/overview/container-type-and-sizes/dry-equipment-specifications.pdf) checked 2026-10-04. Actual dimensions and payload vary by unit and must be confirmed from the equipment plate or carrier documentation.

| Example profile | Inside L × W × H (mm) | Door W × H (mm) | Example payload |
| --- | --- | --- | ---: |
| 20 ft standard dry | 5,896 × 2,350 × 2,393 | 2,350 × 2,274 | 28,200 kg |
| 40 ft standard dry | 12,032 × 2,350 × 2,393 | 2,340 × 2,274 | 28,800 kg |
| 40 ft high-cube dry | 12,032 × 2,350 × 2,697 | 2,340 × 2,577 | 28,620 kg |

An entered custom profile is limited to a closed dry freight container, requires all inside/door/payload values plus a source kind and reference, and is always labeled `unverified_measured`. The equipment-family catalogue marks other container profiles as specification-only, road bodies as manual planning holds, and tank equipment as out of scope for box packing. It is a context list, not a selectable geometry database; see [Maersk family information](https://www.maersk.com/support/faqs/2024/07/01/types-and-sizes-of-containers), [Hapag-Lloyd type groups](https://www.hapag-lloyd.com/de/services-information/cargo-fleet/container/container-type-groups.html), and [KRONE products](https://www.krone-trailer.com/en/products/).

## Validation

```powershell
python manage.py check --settings=dcd_project.settings_demo
python manage.py test optimization.test_mvp_views optimization.test_packing optimization.test_tracking optimization.test_render_deploy --settings=dcd_project.settings_demo
```

This project remains stateless and has no application database or session history. The source was later released on the existing Render Free service; the latest release record and exact source SHA are listed below.

The included browser smoke script exercises manual rows, exact unit conversion, Excel paste, CSV loading/validation, placement and remaining-item details, SVG/table ID parity, row-to-box selection, cargo-fit/full-container camera modes, immutable CSV/JSON exports, and a mocked forecast UI response (no upstream request). It checks the initial desktop first fold and 375 px layout for document-level horizontal overflow, then writes initial, packed desktop, and mobile screenshots. It needs a local Playwright package and Chrome; provide an absolute desktop screenshot path, for example `node scripts/browser-smoke.cjs C:\\temp\\cargo-fit-planner-desktop.png`.

## Marine forecast and AIS status — 2026-10-04

The optional marine form makes an on-demand request only for coordinates entered by the user; it does not identify a vessel or infer its location. Forecast values, requested coordinates, provider grid coordinates, model-valid time, retrieval time, and linked model attribution are displayed separately. Unknown measurements remain unknown. The upstream adapter uses a fixed HTTPS Open-Meteo Marine API endpoint, no credentials, no redirects or retries, a 64 KiB response cap, and a 5-second socket-inactivity timeout (not a strict wall-clock deadline). It uses a process-local 10-minute/32-coordinate cache, a 60-second interval between upstream requests, and a 200-attempt UTC-day budget. These bounds reset on process restart and across multiple workers; they are not a durable quota or service-level guarantee. The feature is for user-confirmed noncommercial educational use under the provider's current API terms. CC BY 4.0 attribution is a separate data-license requirement; attribution links appear with each forecast.

AIS has no active feed or positions. A future server-side integration would require a provider key and compliance with its then-current service and display terms. The UI links to [AISStream's documentation](https://aisstream.io/documentation/) for research context; no AIS connection or credential is configured.

## Live release status — 2026-10-04

The existing `cargo-fit-planner` Render Free service is live from commit `e7120f2092abd3a061ed8061a595f566d82cbe79`. The optional noncommercial marine forecast switch is enabled for the user's confirmed educational portfolio use. The service remains a single stateless instance with no database, disk, or background service. This release does not establish a hard billing cap or promise uptime; see the dated delivery evidence for its bounded live checks and limitations.

## Render deployment path

`render.yaml` describes exactly one native Python web service on the Free plan, with automatic deploys disabled, no database, disk, worker, cron job, cache service, or other managed resource. It targets the confirmed Render workspace and remains separate from all existing services. A Free plan label is not a hard spending cap; public requests and outbound transfer can still have billing implications. The service should only run while the account remains under the explicitly confirmed free-only constraints and without paid upgrades or attached billing methods.

The Render build checkout contains the Git repository, but `scripts/build_render_runtime.py` stages an explicit allowlist into `.render-runtime`; the running process changes into that directory and sets `PYTHONPATH` to that directory only. The staged runtime contains only dedicated Render settings/URL/WSGI entry points, the stateless packer, view, bounded on-demand marine adapter, one template, and no database, legacy settings, routers, models, logs, history, caches, or unrelated files. The tracked SQLite database is not opened, copied into the runtime bundle, or served. Production settings have no installed apps or session middleware and use Django's deny-all dummy database backend. The `healthCheckPath` is `/healthz` and only returns a fixed `ok` response.

The isolated service requires `SECRET_KEY` (at least 50 characters) and Render's canonical `RENDER_EXTERNAL_HOSTNAME` (`*.onrender.com`); it fails closed when either is absent or invalid. `DEBUG` is false, host and CSRF origin are exact, HTTPS redirects and secure CSRF cookies are enabled, and logs go to stdout with query strings omitted. It runs one Gunicorn gthread worker with two threads, an eight-connection accept backlog, bounded request headers, and worker recycling. Compute requests have a process-wide burst of four and refill at one per ten seconds; one compute/export can run at a time, with concurrent work rejected using `503` and `Retry-After`. A raw request-body cap is 800 KiB to allow worst-case percent-encoding expansion; decoded CSV itself is capped at 256 KiB. Each pack expands at most 100 units and makes at most 100,000 global coordinate-candidate checks, retaining the prior 2,000-check per-orientation heuristic limit. This bounds deterministic work but does not promise a per-request deadline or availability under public traffic; rate state resets when the process restarts and public response traffic is not a zero-cost guarantee.

Render Free services can sleep when idle and use ephemeral storage. The application writes no user data to disk and stores no session/history, but cold starts and service availability still require live verification after an authorized deployment. No deployment, public health check, hosted browser walkthrough, billing setting, or account-level spend cap has been verified in this local readiness pass.

Local readiness checks (PowerShell; set the two synthetic environment values before running the production settings check):

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:SECRET_KEY = 'local-test-secret-value-at-least-50-characters-long-000000'
$env:RENDER_EXTERNAL_HOSTNAME = 'cargo-fit-planner.onrender.com'
python manage.py check --settings=dcd_project.settings_render
python manage.py test optimization.test_render_deploy --settings=dcd_project.settings_demo
python manage.py test optimization.test_mvp_views optimization.test_packing --settings=dcd_project.settings_demo
```

`render.yaml` and the allowlist builder are the reproducible native-Python Blueprint path. They do not configure persistent storage or invoke deployment themselves. See the current readiness evidence in `docs/evidence/render-free-readiness-2026-10-03.md`.

## Consolidation follow-up — 2026-11-17 (review branch, not deployed)

Cargo Fit Planner is the active application. The five former Streamlit variants are preserved as complete verified Git bundles on the `relic/legacy-stuffing-20261117` branch. LoadVerse / `3dloder` is also fully backed up privately, because its history contains shipment-item records whose synthetic provenance is unverified. No original repository has been deleted. Archives do not belong in the allowlisted deployed runtime.

The review branch adds:

- **Editable scoped freight quotes:** enter amount, currency, trip/tonne/m³ basis, exact equipment, origin/destination, validity/shipment dates, source and included/excluded charges. Missing/expired/mismatched quotes remain unpriced. Pricing is independent of geometric allocation and applies only to placed cargo. No live-market or universal average is fabricated. The JSON preserves the quote; CSV repeats whole-load estimate fields on each item row, so they must not be summed.
- **Cargo mass distribution:** a genuinely mass-weighted cargo-only centre, midpoint offsets and normalized position are exported. This assumes uniform density within each load unit; it excludes container/vehicle tare and is not axle-load, stability, strength, securing or dispatch certification. Zero placed mass gives unknown coordinates instead of a fictitious midpoint.
- **Vessel/port search and selection boundary:** accepts a ship name, IMO/MMSI, or port code and keeps vessel/port result types distinct. Selecting a result can show provider-attributed identity, position observation time/age/stale status, reported voyage/ETA and speed/course/draught. Missing data stays unknown. The map is opened explicitly and reflects the reported observation, not a refreshed live position. No photographer images are copied.

**Live vessel data is NOT connected.** The default returns a clear unavailable-provider response and makes no vessel request. A trusted server-side provider implementing `search(query, limit=20)` and `detail(identifier)` must first be licensed for directory lookup, position data and public display, and must implement bounded fixed-host transport, secure credentials and quota controls. Set `VESSEL_DATA_PROVIDER` only through reviewed application configuration, never arbitrary user input. MarineTraffic API access is separate from a website subscription; AISStream alone does not guarantee instant global name search or last-known position coverage. There is no scraper or simulated-live fallback.

An optional displayed position uses an [OpenStreetMap embedded map](https://wiki.openstreetmap.org/wiki/Export#Embeddable_HTML) only after clicking the map button; the button discloses that the reported coordinates will be sent to OpenStreetMap. Data attribution is displayed. Coordinates above 85° latitude remain in the detail card without this Mercator map. Vessel position does not establish container association. User-obtained ship identity and the provider's coverage/licensing govern what can be shown.

Validation: 106 backend/view/packing/provider-boundary tests pass with synthetic provider fixtures and no live vessel calls. Rendered JavaScript syntax and Django checks pass. Real-browser interaction and live provider/deployment verification remain outstanding because browser access and Render reauthentication are blocked in the current environment. Do not represent this review branch as deployed or as globally available vessel tracking.

Vessel boundary safeguards: one in-flight request, two-second minimum between uncached provider calls, 60-second/32-key cache and 200 upstream attempts per UTC day, all per process. State resets on restart or additional workers, so this is not a durable billing cap. Displayed observation age updates every 30 seconds without polling the provider; the position itself is never silently extrapolated. Optional reported departure, flag and navigation status remain unknown when absent. Current IMO identities require seven digits; future scheme extensions will need a reviewed update. Provider attribution links use public origins rather than request paths/query strings.

Optional VesselFinder widget: the reviewed branch includes a **disabled-by-default**, user-click-only official map for a known IMO/MMSI. `VESSELFINDER_EMBED_ENABLED=True` may be set in application settings only after confirming the intended use is permitted. No shipped settings enable it. See the [usage and verification limits](docs/evidence/consolidation-2026-11-17.md). It is isolated third-party content, not our global search/detail API; no positions are scraped, and its actual browser behavior remains unverified.

Local personal-use evaluation only: `CARGO_OPEN_WATERS_PERSONAL_DEMO=true` with `dcd_project.settings_demo` opts into the no-key Open Waters name-prefix/MMSI adapter. It is OFF by default and is not activated by Render settings. The API's free tier is personal-use, not authorization for company operations. Coverage can be stale or absent; anonymous IMO and port search are unsupported. Returned source attribution and timestamps remain visible; registry enrichment is deliberately excluded. Read the [evaluation evidence and limitations](docs/evidence/consolidation-2026-11-17.md) before enabling any public deployment.
