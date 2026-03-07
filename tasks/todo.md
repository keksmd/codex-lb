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
