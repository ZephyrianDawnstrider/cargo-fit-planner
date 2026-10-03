# Render Free readiness evidence — 2026-10-03

## Scope and cloud boundary

Prepared a native-Python Render Free service definition for the stateless CSV-to-pack demo. The blueprint has one `web` service, `plan: free`, `runtime: python`, deploy-on-push disabled, no database or disk, and health path `/healthz`. No existing Render service was changed. No cloud resource was created by this source-readiness record.

## Isolation and bounds

`scripts/build_render_runtime.py` stages an exact nine-file allowlist into `.render-runtime`. The service start command changes into that directory and sets `PYTHONPATH=.`. The staged-bundle test verifies only allowlisted files are present, production settings and views import from the bundle, `optimization.models` is unavailable, and no SQLite file exists in the runtime bundle. Production settings use `DEBUG=False`, exact Render host/CSRF origin, required secret and hostname checks, secure cookies/HTTPS/HSTS, no installed apps/session middleware, a deny-all database backend, and stdout logging. `/healthz` is a GET-only fixed response and is exempt from Django's HTTPS redirect for platform probes.

Request admission uses a process-wide four-request burst with one token refilled every ten seconds, a nonblocking single-compute slot, an 800 KiB bounded raw-body read before CSRF/form parsing, and a 256 KiB decoded CSV limit. The packer accepts at most 100 expanded units, IDs up to 64 characters, names up to 120 characters, preserves the prior 2,000 candidate checks per orientation, and adds a 100,000 coordinate-candidate budget per pack with an explicit exhaustion reason. Exports recompute from the submitted immutable CSV, neutralize spreadsheet formulas, and use `Cache-Control: no-store`. The one-worker/two-thread configuration and admission limits do not promise a strict per-request deadline or service availability.

The tracked `db.sqlite3` was inspected read-only at schema/table-count level only. It contains Django scaffold tables; `auth_user`, `django_session`, and `django_admin_log` had zero rows, with 24 permission and 6 content-type metadata rows. No row values were read. SHA-256 remained `bf0fa0bde9014bce7c9a8135775cff0efa53b6118f5491014b6ae4fec27d2d7e` before and after. The bundle does not include or open this database; the full repository remains the configured Git source, while the running process imports only the staged bundle.

## Local verification

- Tested in an isolated venv under `work/cargo-render-check/.venv`: Python 3.14.6, Django 6.1.1, Gunicorn 23.0.0.
- `python manage.py test optimization.test_mvp_views optimization.test_packing optimization.test_render_deploy --settings=dcd_project.settings_demo`: 44 tests passed in the last full run; the staged-bundle test then passed separately after its subprocess was corrected to invoke the production WSGI entry point and set `DJANGO_SETTINGS_MODULE=dcd_project.settings_render`. It verified health, pack, CSV export, JSON export, no-store headers, and bundle-only module resolution.
- `python manage.py check --settings=dcd_project.settings_render`: no issues.
- `git diff --check`: passed.
- Docker Desktop Linux engine was unavailable, so no Docker build was attempted; the deployment definition uses the native Python runtime.

## Not proven here

This evidence is a local source/build-bundle check, not a deployed-service acceptance. At the time of this record, hosted health, public CSV validation/pack/export, mobile/browser behavior, cold start, restart/ephemeral-storage behavior, and account billing controls are not verified. Render Free services can sleep and have ephemeral storage. The service is stateless and writes no user manifests or history, but a Free plan label is not a hard spending cap; public responses and outbound transfer can still have billing implications. Keep the explicit Free-only/no-card constraints and do not add paid resources.
