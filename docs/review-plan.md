# Code Review Notes & Implementation Plan

## Findings
- **Update endpoints are unauthenticated**: `/api/updates/*` can trigger `git pull`, migrations, and systemctl restarts without any guard. On a “trusted” LAN this is still risky for accidental/malicious calls.
- **Frontend/backend URL coupling**: Components hardcode `API_URL = ''`, and WebSocket hook always dials `/ws` on the frontend host. This only works when nginx proxies both REST and WS; dev without a proxy breaks, and WS relies on an implicit proxy.
- **API client path mismatch**: Frontend control client calls `/api/control/fixture/:id` and `/api/control/group/:id` but the backend exposes `/api/control/fixtures/{id}` and `/api/control/groups/{id}`.
- **Docker healthcheck dependency missing**: Healthcheck runs `python -c "import requests" ...` but `requests` is not in `daemon/requirements.txt`, so healthcheck fails in slim images.
- **ORM model registration incomplete**: `_import_models` omits several models (SystemSetting, Override, software update tables), leading to incomplete metadata if tables are ever generated via `Base.metadata.create_all` or autogenerate.
- **Performance guardrails**: Switch handling fetches group defaults from the DB on every press; DMX output is sent every loop iteration even when values haven’t changed.

## To-Do (implementation order)
1) Add a review/security note to updates API: introduce optional shared-secret header driven by config so updates require `X-Update-Token` when set.
2) Fix frontend URL handling: centralize API/WS URLs (respect `NEXT_PUBLIC_API_URL`/`NEXT_PUBLIC_WS_URL`), update hooks/pages to consume that, and avoid hardcoded `''`.
3) Correct control endpoint paths in the frontend API client.
4) Add `requests` to `daemon/requirements.txt` to satisfy the Docker healthcheck.
5) Ensure `_import_models` imports all models (system settings, overrides, software update tables) for accurate metadata/migrations.
6) Add lightweight performance improvements:
   - Cache group default lookups in `SwitchHandler`.
   - Avoid redundant DMX writes in `LightingController` by skipping unchanged outputs.

## Rollback
- All changes are on branch `review-audit`. Checkout `main` or revert this branch to return to the current production version on the Pi.
