# Cargo Fit Planner — local MVP

This local MVP adds a deterministic synthetic-cargo walkthrough to the existing Django project. It accepts a strict CSV file or pasted CSV, expands quantity into stable item IDs, runs the feasibility packer, and shows placed coordinates, remaining cargo, an isometric view, and CSV/JSON exports. Validation reports row and field details (up to 20 at a time) while preserving the submitted CSV. Item ID controls connect placed-table rows to the rendered boxes. The displayed container is one published 20 ft standard example; it is not a universal profile or an optimality claim. Cost is omitted.

Repository: [ZephyrianDawnstrider/cargo-fit-planner](https://github.com/ZephyrianDawnstrider/cargo-fit-planner).

## Run locally

Use Python 3.12 or newer. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-demo.txt
.\run_demo.ps1
```

Open `http://127.0.0.1:8762/`, select **Load synthetic example**, then **Pack cargo**. Download the CSV template from the page. Demo settings replace the legacy SQL Server databases and routers with in-memory SQLite, disable file logging, and do not read or write the tracked runtime database. Use only synthetic data in this local demonstration. The original database-backed route remains at `/` with the default settings; the isolated demo settings use a separate URL map and do not enable that environment.

The packing result is a deterministic feasibility heuristic. It handles rectangular dimensions, doorway and container fit, overlap, the published payload limit, and conservative support rules for stackability. A cargo item marked `stackable=true` may support cargo above it; a `false` item may sit on the floor or on a different supporting item, but cannot support another item. The packer does not model load strength, lashing, floor point loads, loading sequence/access, or special handling. Review carrier-specific container documentation before operational use. Displayed weight and volume percentages are simple ratios against published payload and internal volume; they do not predict fit because the volume ratio ignores gaps, orientation, support, and access.

CSV input is limited to 256 KiB in the demo route, 100 source rows, and 100 expanded units. Dimensions must be whole millimetres (1 mm resolution); weight accepts 0.001 kg increments. Columns are `item_id,name,length_mm,width_mm,height_mm,weight_kg,quantity,stackable,orientation`; stackable accepts true/false, yes/no, or 1/0, and orientation accepts `fixed` or `yaw`. See the [profile source](https://www.hapag-lloyd.com/en/services-information/cargo-fleet/container/20-standard.html); the published example is 5900 × 2352 × 2395 mm inside, 2340 × 2292 mm at the door, with 28,130 kg max payload (source checked 2026-10-03).

## Validation

```powershell
python manage.py check --settings=dcd_project.settings_demo
python manage.py test optimization.test_mvp_views optimization.test_packing --settings=dcd_project.settings_demo
```

This branch is a local review candidate. No live service deployment or database connection is part of the demo.

The included browser smoke script exercises multi-row validation, synthetic CSV loading, placement and remaining-item details, SVG/table ID parity, keyboard-operable row-to-box selection, view-angle redraw, CSV and JSON downloads, and snapshot consistency after editing the input. It also checks 375 px layout for document-level horizontal overflow and writes desktop and mobile screenshots. It needs a local Playwright package and Chrome; provide an absolute desktop screenshot path, for example `node scripts/browser-smoke.cjs C:\\temp\\cargo-fit-planner-desktop.png`.
