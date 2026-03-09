# Todo
- [x] Align Docker and local database paths so both use the same SQLite file via the host-mounted data directory.
- [x] Update docker-compose.yml to mount the correct host path and override container DB env to /var/lib/codex-lb/store.db.
- [x] Provide verification steps to confirm local + docker share data.

# Review
- [x] Verify docker-compose.yml mounts `${HOME}/.codex-lb` to `/var/lib/codex-lb` and sets `CODEX_LB_DATABASE_URL` for the container.
- [x] Confirm the local app still uses `~/.codex-lb/store.db` when run outside Docker.

## Refresh Token Endpoint Hardening
- [x] Add explicit refresh token endpoint resolver with default `https://auth.openai.com/oauth/token`.
- [x] Support `CODEX_REFRESH_TOKEN_URL_OVERRIDE` env override for refresh token exchange endpoint.
- [x] Keep refresh request payload aligned with OAuth refresh contract (`client_id`, `grant_type`, `refresh_token`, `scope`).
- [x] Add unit tests for default endpoint, override endpoint, and refresh request payload.

## Review (Refresh Token Endpoint Hardening)
- [x] Confirm refresh exchange posts to the resolved endpoint and not a derived base URL path.
- [x] Confirm request payload uses client id `app_EMoamEEZ73f0CkXaXp7hrann` and scope `openid profile email`.

## CI Bugfix: SPA Static Dir And Usage Deactivation
- [x] Reproduce the SPA fallback and usage updater CI failures locally.
- [x] Ensure the SPA static directory exists in clean checkouts before serving or test setup writes.
- [x] Update the outdated usage updater test to match the intended no-auto-deactivation behavior.
- [x] Verify the targeted tests pass locally.

## Review (CI Bugfix: SPA Static Dir And Usage Deactivation)
- [x] Confirm SPA fallback still returns `503` with the frontend build hint when `index.html` is missing.
- [x] Confirm usage updater does not auto-deactivate on `402`, `401`, `429`, or `5xx`.

## Deployment Incident: codex-proxy-prod
- [x] Reproduce the live deployment failure from readonly cluster inspection.
- [x] Fix image/runtime assumptions that block the app in Kubernetes.
- [x] Fix Argo-managed storage, env, and healthcheck wiring for `codex-proxy`.
- [x] Verify local rendering/tests for the deployment changes.
- [x] Confirm the live rollout becomes healthy after Argo sync.

## Review (Deployment Incident: codex-proxy-prod)
- [x] Confirm migrations target a writable persistent path in-cluster.
- [x] Confirm the app binds the same port that the service and probes target.
- [x] Confirm the rendered Helm manifest includes a valid PVC mount and valid `db-dir` volume source.

## Logging Cleanup In Container
- [x] Remove noisy uvicorn access logs from the runtime/container startup path.
- [x] Ensure application logs are emitted to container stdout/stderr with a predictable format and level.
- [x] Add `info`/`debug` logs to key startup and proxy service paths if current coverage is insufficient.
- [x] Verify the resulting runtime output locally so container-visible app logs remain while access logs are suppressed.

## Review (Logging Cleanup In Container)
- [x] Confirm `uvicorn.access` no longer emits per-request access lines in the default app startup path.
- [x] Confirm application lifecycle logs appear during startup/shutdown.
- [x] Confirm proxy/service request handling still emits useful app-level logs for debugging without excessive noise.

## Auth Import/Export Improvements
- [x] Create OpenSpec change for multi-file auth import, import-time refresh, and zip export.
- [x] Update dashboard/backend specs and task notes for the new account import/export behavior.
- [x] Implement backend multi-file import response flow with per-file success/failure reporting.
- [x] Refresh imported auth immediately when the access token is expired but refresh token is still usable.
- [x] Add backend zip export endpoint that packages current account auth payloads with current tokens.
- [x] Update frontend account import dialog and mutations for multi-file upload.
- [x] Add frontend download action for exporting all current auth payloads as zip.
- [ ] Verify backend/frontend tests covering batch import, import-time refresh, and zip export.

## Review (Auth Import/Export Improvements)
- [x] Confirm the frontend batch import uses a dedicated batch endpoint without regressing the single-file import contract.
- [x] Confirm an imported file with expired access token and valid refresh token is persisted with refreshed tokens immediately.
- [x] Confirm the export action downloads a zip containing one current auth payload per account.

## Frontend: Accounts Batch Import UX
- [x] Update frontend accounts API/schemas to use batch import and auth zip download endpoints.
- [x] Replace single-file import dialog with multi-file import UX on the accounts page.
- [x] Add blob download helper if needed and wire the "download all auth" action.
- [x] Update frontend tests and MSW mocks to the new accounts import/download contract.
- [ ] Verify targeted frontend tests pass locally.

## Review (Frontend: Accounts Batch Import UX)
- [x] Confirm accounts import submits multiple files to `POST /api/accounts/import/batch`.
- [x] Confirm the accounts page exposes a zip download action for all auth exports.
- [x] Confirm frontend tests/mocks match the new endpoint set and response shapes.

## CI Bugfix: Upstream Error Reset Metadata Access
- [x] Reproduce and isolate the integration failures caused by upstream error reset metadata access in proxy/rate-limit flows.
- [x] Fix proxy/load-balancer handling so dict-backed `UpstreamError` payloads are consumed safely in all retry and logging paths.
- [x] Verify the previously failing integration tests pass locally.

## Review (CI Bugfix: Upstream Error Reset Metadata Access)
- [x] Confirm stream retry, compact error propagation, sticky session failover, and `/v1/responses` flows no longer crash on dict-backed upstream errors.
- [x] Confirm rate-limit and quota handling still preserve reset metadata when present.

## Usage/Auth/Proxy Bugfixes
- [x] Sanitize usage-fetch 403 failures so logs/errors do not dump upstream HTML bodies.
- [x] Fix account token status display so stored refresh tokens do not leave the account shown as only `Expired`.
- [x] Add an HTTP proxy option through the dashboard settings flow and apply it to outbound HTTP clients.
- [x] Add/update backend and frontend tests for the new behavior.
- [ ] Verify targeted backend and frontend tests pass locally.

## Review (Usage/Auth/Proxy Bugfixes)
- [x] Confirm a 403 usage fetch surfaces a compact message without embedding full HTML response bodies.
- [x] Confirm accounts with expired access tokens but stored refresh tokens show recoverable token state in the UI.
- [x] Confirm the configured HTTP proxy setting is persisted by `/api/settings` and used by outbound HTTP requests.

## Testcontainers Migration Bootstrap
- [x] Reproduce the backend test fixture failure mode where testcontainer databases start without migrated tables.
- [x] Change the shared backend test reset fixtures to rebuild schema through Alembic migrations instead of ORM `create_all`.
- [x] Verify representative backend tests pass against the migrated fixture flow.

## Review (Testcontainers Migration Bootstrap)
- [x] Confirm `db_setup` and app-backed integration fixtures create schema via `run_startup_migrations()`.
- [x] Confirm tests no longer depend on `Base.metadata.create_all()` bypassing migrations, except the dedicated raw migration fixture used to exercise legacy bootstrap paths.

## Optional Proxy API Key Header (`X-Codex-Proxy-Key`)
- [x] Keep `Authorization: Bearer` validation as the primary proxy auth mechanism.
- [x] Add `X-Codex-Proxy-Key` as an optional additional guard (enabled via env config).
- [x] Enforce that when optional proxy-key guard is enabled, requests must provide a matching `X-Codex-Proxy-Key` value.
- [x] Add integration/unit tests covering valid/invalid/missing/misconfigured optional proxy-key guard behavior.
- [x] Verify targeted auth/config tests pass.

## Review (Optional Proxy API Key Header)
- [x] Confirm `Authorization: Bearer <key>` continues to work.
- [x] Confirm `X-Codex-Proxy-Key` is not an alternative bearer credential path.
- [x] Confirm when proxy-key guard is enabled, valid bearer + valid `X-Codex-Proxy-Key` is required.
- [x] Confirm misconfigured enabled guard (no configured key) fails closed.
