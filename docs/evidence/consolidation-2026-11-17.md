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
