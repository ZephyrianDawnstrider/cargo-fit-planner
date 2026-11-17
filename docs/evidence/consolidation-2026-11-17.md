# Consolidation follow-up evidence — 2026-11-17

## Preserved histories
Five complete legacy Streamlit bundles are on the Cargo Fit Planner `relic/legacy-stuffing-20261117` branch. Each was restored locally and checked with strict git fsck; the public remote copies were fetched again, bundle-verified and SHA-256 checked. Full LoadVerse history remains private because embedded job records are not established synthetic. Nothing deleted or deployed.

## Application checks
- 106 tests passed: `python manage.py test optimization.test_pricing optimization.test_vessels optimization.test_mvp_views optimization.test_packing optimization.test_tracking optimization.test_render_deploy --settings=dcd_project.settings_demo`.
- `manage.py check --settings=dcd_project.settings_demo` passed.
- Two JavaScript blocks rendered from a packed result page passed `node --check`.
- `git diff --check` passed.
- Pricing validation/export tests use synthetic quote data; vessel tests inject a synthetic adapter and never contact an AIS provider.

## Browser/access limits
Chromium failed creating required sockets in this execution environment, including after an escalation attempt. Cloud browser access to the local app was unavailable/rejected. This is not a real-browser pass. Render's workspace lookup requires reconnection, and no service/deployment was changed. A licensed vessel provider is not configured: the real endpoint returns unavailable rather than fake data.

## Scope
Pricing does not affect placements. Cargo centre-of-mass diagnostics are not operational safety checks. Top-load strength, axle/floor point loads, securing and loading sequence remain unmodeled. The vessel search/map UI is provider-ready plumbing, not finished live tracking. No universal coverage, live GPS, quoted-price freshness or deployment availability is claimed.

Vessel boundary safeguards: one in-flight request, two-second minimum between uncached provider calls, 60-second/32-key cache and 200 upstream attempts per UTC day, all per process. State resets on restart or additional workers, so this is not a durable billing cap. Displayed observation age updates every 30 seconds without polling the provider; the position itself is never silently extrapolated. Optional reported departure, flag and navigation status remain unknown when absent. Current IMO identities require seven digits; future scheme extensions will need a reviewed update. Provider attribution links use public origins rather than request paths/query strings.

## Optional official VesselFinder widget (disabled)
Reviewed https://www.vesselfinder.com/embed and https://www.vesselfinder.com/terms on 2026-11-17. Official documentation invites website embedding using `aismap.js`, a seven-digit IMO or nine-digit MMSI and optional 24-hour track; no name-search parameter is documented. Terms restrict free access to personal/internal purposes and prohibit third-party redistribution/benefit absent express permission. The invitation does not clearly settle use in a public commercial logistics product. Consequently `VESSELFINDER_EMBED_ENABLED` remains absent/false in every shipped setting. A deployment owner must confirm appropriate usage rights before explicitly setting it true; this is not an environment toggle silently activated by this PR.

When enabled for permitted use, the visitor must click a disclosed button before the third-party script loads. The fixed official script runs in an opaque-origin sandboxed frame, never the app document; only a validated identifier/track preference is inserted. No cargo, quote or shipment fields are passed, no upstream API keys are needed, and the app does not extract or store the widget's positions, imagery or data. Attribution, source terms/privacy links and no-navigation/coverage warnings are retained. Source script can change; the restrictive sandbox may prevent features/cookies/popups from working. Actual widget loading/position availability has NOT been browser-verified, so this is a gated demo, not a claimed working live-provider substitute. Do not loosen the sandbox without a security review. Three additional boundary tests cover off-by-default gating, numeric validation, sandboxing and non-forwarding of cargo fields.
