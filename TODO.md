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

## 2026-10-03 — Cargo Fit Planner UI refinement

The follow-up UI scope adds structured row-level CSV errors, actionable remaining-item details, explicit source-row versus expanded-unit and weight summaries, clearly bounded capacity ratios, accessible item-to-box selection that survives view redraw, and richer CSV export rows. The original MVP acceptance record above remains historical; refinement checks and browser screenshots are recorded in `docs/evidence/cargo-fit-planner-refinement-2026-10-03.md` after verification.

## 2026-10-03 — Cargo Fit Planner refinement acceptance

The refinement is verified: 28 focused tests pass, Django reports no system check issues, and the headless browser walkthrough passes at desktop and 375 px without document overflow or console errors. The evidence record above documents the validation, tables, summaries, selection interaction, exports, and screenshots. Local delivery identity and remote URL are documented after repository rename in the delivery receipt; earlier status sections remain historical.

## 2026-10-03 — Render Free readiness candidate (cloud hold)

An isolated, stateless Render Docker/Blueprint candidate is being prepared with fail-closed production settings, a health endpoint, bounded inputs and compute admission, and an image/build-context allowlist. This does not authorize or record cloud resource creation. Zero-cost/billing safeguards remain unresolved; hosted health/browser behavior, account secrets, and public service availability are not proven. See `docs/evidence/render-free-readiness-2026-10-03.md` for current checks and blockers; all earlier TODO and acceptance notes remain historical.

## 2026-10-03 — Native Python service path supersedes draft

After manager confirmation that the selected Render workspace has no payment card attached and the human authorized a Free-only service, the deployment path is a native Python web service, not the unbuildable local Docker path. The source bundle is staged from an explicit allowlist; readiness and account/service creation evidence are appended to `docs/evidence/render-free-readiness-2026-10-03.md`. The earlier cloud-hold note records the state before this authorization and is preserved as historical.
