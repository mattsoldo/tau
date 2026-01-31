# Software Update Review (2026-01-31)

## Recommendation (rewrite vs fix)
Do not do a full rewrite. The core design (GitHub Releases + backup + rollback) is workable, but there are several blocking defects and reliability gaps. Fixing these and adding a small amount of infrastructure (background job + persisted state + privileged installer) should make the feature reliable without a full redesign.

## Likely root causes of consistent failure
- .deb install path runs dpkg/apt-get without sudo, so installs fail for the non-root tau service user. (daemon/src/tau/services/software_update_service.py:1145-1177)
- Release asset selection prefers .deb packages, so the failing install path is the default. (daemon/src/tau/services/github_client.py:234-255)
- The restart command uses `sudo systemctl restart tau-daemon tau-frontend`, which does not match the sudoers entries that only allow single-service restarts; restart likely fails silently. (daemon/src/tau/services/software_update_service.py:596-602, daemon/deployment/tau-sudoers:12-15)
- Update runs synchronously in the HTTP request; long steps (download, build, migrations) likely exceed proxy timeouts so the UI reports failure even if work continues. (daemon/src/tau/api/routes/software_updates.py:226-266)
- Default backup location `/var/lib/tau-lighting/backup` is typically root-owned; backup creation will fail if the directory is not pre-created and owned by tau. (daemon/src/tau/models/software_update.py:236-248, daemon/src/tau/services/backup_manager.py:210-219)

## Findings (ordered by severity)
### Critical
1) Non-privileged package install
- The update flow attempts `dpkg -i` and `apt-get install -f` without sudo. On a standard systemd deployment, the daemon runs as user `tau`, so this consistently fails. (daemon/src/tau/services/software_update_service.py:1145-1177)

2) Restart command does not match sudoers rule
- Sudoers only allows restarting a single service per command, but the update code invokes a combined restart; this is likely blocked and leaves old code running. (daemon/src/tau/services/software_update_service.py:596-602, daemon/deployment/tau-sudoers:12-15)

3) Update execution tied to request lifecycle
- `/api/system/update/apply` runs the entire update inline instead of backgrounding it, increasing the likelihood of HTTP timeouts and user-visible failure. (daemon/src/tau/api/routes/software_updates.py:226-266)

### High
4) Backup directory permission mismatch
- Default backup location is under `/var/lib`, which is commonly root-owned; the service does not handle permission errors here, so backup creation can fail early. (daemon/src/tau/models/software_update.py:236-248, daemon/src/tau/services/backup_manager.py:210-219)

5) Downgrade download is broken by wrong argument name
- `download_asset` is called with `checksum=` instead of `expected_checksum=`, causing a TypeError and consistent downgrade failures. (daemon/src/tau/services/software_update_service.py:878-883)

### Medium
6) Update state/progress is per-request only
- State is stored in instance fields and a new service is created per request; status endpoints cannot accurately report progress or recover after restarts. (daemon/src/tau/services/software_update_service.py:118-122, daemon/src/tau/api/routes/software_updates.py:160-177)

7) Migration failures are ignored
- `_run_migrations` logs warnings but does not fail the update, which can leave the system in a broken post-update state. (daemon/src/tau/services/software_update_service.py:1241-1266)

8) Rate limit logging violates DB constraints
- `rate_limited` is not a valid `update_checks.result` value, so the log write can fail and mask the real error. (daemon/src/tau/services/software_update_service.py:313-317, daemon/src/tau/models/software_update.py:191-199)

9) No dependency update for backend when using tarball installs
- The OTA flow does not run pip/venv updates, so new dependencies can break after update. (daemon/src/tau/services/software_update_service.py:564-587)

### Low
10) Update endpoints lack the shared-secret protection used by legacy update routes
- `/api/system/update/*` does not enforce `X-Update-Token`, increasing risk of unauthorized update attempts on a trusted LAN. (daemon/src/tau/api/routes/software_updates.py:160-177, daemon/src/tau/api/routes/updates.py:17-31)

## Recommended fixes (prioritized)
### 1) Make installs succeed under the tau user
- Option A: Prefer tarball assets and avoid dpkg entirely; ensure release artifacts include built frontend + pinned backend deps.
- Option B: Keep .deb, but move install to a dedicated systemd update service that runs as root and is invoked via `systemctl start tau-update@<version>.service` with tight sudoers rules.

### 2) Run updates as background jobs with persisted state
- Move apply/rollback/downgrade into a background job (Celery, RQ, or a simple asyncio task with DB persisted state). The API should return a job id and status endpoint should read state from DB.
- Persist state transitions in a table (or reuse `update_log`) so the UI can show progress across restarts.

### 3) Fix restart and migration handling
- Restart services via two separate sudo calls or update sudoers to allow the combined command.
- Treat migration failures as fatal and trigger rollback immediately.

### 4) Stabilize backups and permissions
- Change default backup directory to a tau-owned path (e.g., `/opt/tau-backups`) and ensure install scripts create/own it.
- Add a preflight check to show a clear error before starting the update.

### 5) Fix downgrade bug
- Change `checksum=` to `expected_checksum=` in `download_asset` call.

## Libraries/frameworks to consider (if you want to lean on proven tooling)
- TUF (The Update Framework): secure metadata, signed targets, and rollback protection for update distribution.
- RAUC / SWUpdate / Mender: embedded Linux OTA frameworks that handle A/B updates, atomic deploys, and rollback.
- OSTree (or rpm-ostree): atomic filesystem deployments and rollback for Linux systems.

## Rewrite decision
A full rewrite is not required. Address the critical/high issues above, add a background execution model with persisted state, and you should have a stable update system in weeks rather than months.

## Open questions
- What format do current GitHub Releases ship (deb vs tar.gz) and are they pre-built with frontend artifacts?
- Is Node.js guaranteed on production devices, or should we avoid building frontend on-device?
- Do you want updates to be fully offline-capable (local .deb/.tar.gz upload) as a fallback?
