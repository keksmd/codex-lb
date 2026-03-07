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
