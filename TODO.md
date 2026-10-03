# TODO: Fix Consistency Between Stuffing Table and 3D Model

## Tasks
- [x] Modify create_3d_model in utils.py to return list of placed items
- [x] Update views.py to filter packed items to only placed ones, move unplaced to remaining
- [x] Recalculate total weight and volume for containers after filtering
- [ ] Test with provided data to ensure non-stackable cargo is handled correctly
- [ ] Verify item counts match between table and 3D model


## 2026-10-03 — Cargo MVP branch status

A separate synthetic CSV-to-pack demo is being added on branch cargo-mvp; the original database-backed workflow and prior TODO evidence above are retained. The MVP uses one published 20 ft standard example and reports feasible placement, remaining items, item coordinates, and exports. It does not claim optimal packing or verified pricing. Current scoped work: finish UI integration, isolated local setup, and browser verification before review.

## 2026-10-03 — Cargo MVP acceptance supersedes prior status

The synthetic cargo MVP implementation, isolated setup, focused checks, and headless browser walkthrough are complete. CSV upload, quantity conservation, feasibility output, remaining-item reasons, SVG/table ID parity, and both exports passed the recorded checks in `docs/evidence/cargo-mvp-2026-10-03.md`. The earlier status above is retained as historical progress; this section records the later acceptance result. Main-branch delivery identity is recorded in the user-facing delivery receipt.
