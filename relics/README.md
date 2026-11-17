# Relics: original stuffing application histories

Captured 2026-11-17. These Git bundles preserve all reachable refs exposed at capture time for the five original Streamlit repositories. Main applications and originals are unchanged. This branch is an archive, not a deployment source; do not merge its bundle files into the production runtime.

| Repository | Commits |
|---|---:|
| container-stuffing20fc | 15 |
| container-stuffing-dcd | 5 |
| container-stuffing-dnd | 15 |
| container-stuffing-40hc | 7 |
| container-stuffing-40fc | 9 |

All bundle contents were independently restored and verified using `git bundle verify` and `git fsck --full --strict`. Private-repo reconstruction preserved exact original commit/tree/blob hashes. SHA256SUMS covers each bundle. The 40fc bundle includes its consolidation and pull-request refs as captured. Original authors, dates, messages and historical versions are retained.

Restore with `git clone --mirror container-stuffing-dcd.bundle restored.git`, then `git -C restored.git fsck --full --strict`. Verify checksums before restoration.

LoadVerse (`3dloder`) was also fully backed up privately. Its history contains embedded shipment-item records of unverified synthetic provenance, so it is deliberately not republished here. The owner retains the full private history archive. No record-level data from it is copied into Cargo Fit Planner.

These backups do not preserve GitHub issues, account/repository settings, deployed services, permissions or deleted/unexposed refs. No source repository has been deleted. Before any deletion, verify independent durable backups and obtain a specific action-time approval; archiving the originals is safer when only decluttering is needed.

Historical rate constants are unverified legacy rules, not current quotes or market averages. Code publication was explicitly authorized by the owner; this grants no additional third-party data rights.
