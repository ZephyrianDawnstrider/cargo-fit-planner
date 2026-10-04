# Cargo Fit Planner Phase 1 local verification — 2026-10-04

This record covers the cargo-profile/load-unit refinement before its app commit and hosted rollout. It supplements earlier dated evidence and does not replace it.

## Source and behavior

- Adds named 20 ft standard dry, 40 ft standard dry, and 40 ft high-cube dry example profiles, plus an unverified custom-measured closed dry freight-container profile with required measurement provenance.
- Adds load-unit, floor-only, and dangerous-goods manifest fields. Dangerous goods remain unplaced under a visible manual-compliance hold; this tool does not approve IMDG classification, segregation, stowage, carrier acceptance, booking, or dispatch.
- Keeps feasibility results, shipment references, profile provenance, and safe CSV/JSON exports tied to the submitted snapshot. The heuristic does not assess loading order, securing, floor bearing, cargo strength, road/axle limits, or special-equipment geometry.
- The family catalogue is informational: other container profiles are specification-only, road freight bodies are manual-planning holds, and tank equipment is out of scope for box packing.

## Checks

- `python manage.py test optimization.test_mvp_views optimization.test_render_deploy --settings=dcd_project.settings_demo`: **33 passed**; Django system checks reported no issues.
- Solver-owned `optimization.test_packing`: **33 passed**, as reported by the solver before integration. The UI/view suite and solver suite were not combined into one run.
- `node --check scripts/browser-smoke.cjs`: passed. `git diff --check`: passed (Git reported only the existing Windows LF-to-CRLF checkout warnings).
- Fresh local headless Chrome context, running the demo settings at `http://127.0.0.1:8762/`: browser smoke exited 0 with no console errors. It exercised manual entry, exact unit conversion, named 40HC and custom profile snapshots, extended and legacy TSV, extended CSV import, malformed CSV preservation, DG hold details, immutable exports, SVG/table ID parity, and the remaining-panel width/order and mobile summary.
- Browser results: 9 expanded units, 8 placed and 1 DG-held; desktop first fold showed entry and preview; mobile viewport width and document scroll width were both 375 px. The remaining-cargo panel appears full-width between packing results and optional weather. Mobile summary shows the held item’s dimensions, weight, type, UN number, class, group, and human-readable hold reason.
- Fresh local screenshots (not hosted captures):
  - `outputs/cargo-fit-planner-vnext-2026-10-04-review2-initial.png`
  - `outputs/cargo-fit-planner-vnext-2026-10-04-review2-desktop.png`
  - `outputs/cargo-fit-planner-vnext-2026-10-04-review2-mobile.png`
  - `outputs/cargo-fit-planner-vnext-2026-10-04-review2-custom-catalogue.png`
- Weather UI was exercised only with the smoke script’s mock fixture; this local browser run made no upstream forecast request.

## Data custody and release boundary

- Local checkout base before this change: `e4a3d29ca7c90e83db57154f9f7720784fd68f99`; branch `main`. No phase-1 commit or deploy is represented by this record.
- Tracked `db.sqlite3` SHA-256 is `bf0fa0bde9014bce7c9a8135775cff0efa53b6118f5491014b6ae4fec27d2d7e`, matching the prior readiness record. No row values were read. The database was not modified or included in the isolated Render runtime.
- The paused GDACS files remain preserved outside the repository at the task’s `work/parked-gdacs-2026-10-04` location; this phase does not include or activate them.
- The source/readiness record is not a hosted acceptance. Live deployment, hosted CSV/export behavior, account limits, cold start, and physical restart behavior require their separate release checks.
