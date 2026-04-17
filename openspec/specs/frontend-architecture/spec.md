# frontend-architecture Specification

## Purpose

See context docs for background.

## Requirements
### Requirement: Vite project structure

The frontend SHALL be a standalone Vite + React + TypeScript project located at `frontend/` in the repository root. The build output SHALL target `app/static/` so that FastAPI serves the built assets without configuration changes.

#### Scenario: Development server

- **WHEN** the developer runs `npm run dev` in `frontend/`
- **THEN** the Vite dev server starts with HMR and proxies `/api/*`, `/v1/*`, `/backend-api/*`, `/health` requests to the FastAPI backend

#### Scenario: Production build

- **WHEN** the developer runs `npm run build` in `frontend/`
- **THEN** Vite outputs optimized assets (JS, CSS, index.html) to `app/static/` with content-hashed filenames

### Requirement: SPA routing
The application SHALL use React Router v6 for client-side routing with four routes: `/dashboard`, `/accounts`, `/settings`, `/firewall`. The root path `/` SHALL redirect to `/dashboard`. FastAPI SHALL serve `index.html` for all unmatched routes as a SPA fallback.

#### Scenario: Direct navigation to route
- **WHEN** a user navigates directly to `/firewall` in the browser
- **THEN** FastAPI serves `index.html` and React Router renders the Firewall page

#### Scenario: Client-side navigation
- **WHEN** a user clicks the "Firewall" tab from another page
- **THEN** the URL changes to `/firewall` without full page reload and the Firewall page renders

### Requirement: Authentication gate

The application SHALL check the session state via `GET /api/dashboard-auth/session` on initial load. When `passwordRequired` is true and `authenticated` is false, the application MUST render only the login form. All other routes and UI elements MUST be hidden until authenticated.

#### Scenario: Unauthenticated load with password required

- **WHEN** the app loads and the session endpoint returns `{ "passwordRequired": true, "authenticated": false }`
- **THEN** only the login form is visible; navigation tabs and page content are not rendered

#### Scenario: Authenticated load

- **WHEN** the app loads and the session endpoint returns `{ "authenticated": true }`
- **THEN** the full application with navigation tabs and default page (Dashboard) is rendered

#### Scenario: TOTP verification pending

- **WHEN** the session returns `{ "passwordRequired": true, "authenticated": false, "totpRequiredOnLogin": true }` and the user has completed password login
- **THEN** a TOTP input dialog is shown; the full UI is not accessible until TOTP verification succeeds

### Requirement: Theme support

The application SHALL support light and dark themes using Tailwind CSS dark mode (class strategy). The theme preference MUST be persisted to localStorage and applied on load. A theme toggle button MUST be visible in the application header.

#### Scenario: Theme toggle

- **WHEN** a user clicks the theme toggle button
- **THEN** the theme switches between light and dark and the preference is saved to localStorage

#### Scenario: Theme persistence

- **WHEN** the app loads with a previously saved theme preference
- **THEN** the saved theme is applied immediately without flash

### Requirement: Dashboard page

The Dashboard page SHALL display: summary metric cards (requests 7d, tokens, cost, error rate), primary and secondary usage donut charts with legends, account status cards grid, and a recent requests table with filtering and pagination.

#### Scenario: Dashboard data load

- **WHEN** the Dashboard page is rendered
- **THEN** the app fetches `/api/dashboard/overview` (accounts, summary, windows) and `/api/request-logs` (recent requests) in parallel, rendering all dashboard sections with the combined data

#### Scenario: Auto-refresh

- **WHEN** the Dashboard page is active
- **THEN** the dashboard overview and request logs are independently refetched at a regular interval (30 seconds)

#### Scenario: Request log filtering

- **WHEN** a user applies filters (search, timeframe, account, model, status) to the request logs table
- **THEN** only the request logs query refetches from `/api/request-logs` with the applied filter parameters; the dashboard overview is NOT refetched

#### Scenario: Request log pagination

- **WHEN** a user changes the page size or navigates to the next page
- **THEN** the request logs query refetches with updated offset/limit parameters and the response includes `total` count and `has_more` flag for pagination state

### Requirement: Request logs display fast-mode service tier
When a request log entry includes `service_tier`, the dashboard request-log API response MUST expose it and the recent-requests UI MUST render it alongside the model label.

#### Scenario: Fast-mode request log entry is visible
- **WHEN** a request log entry is recorded with `service_tier: "priority"`
- **THEN** the `GET /api/request-logs` response includes `serviceTier: "priority"`
- **AND** the dashboard recent-requests table renders the model label with the priority tier visible

### Requirement: Request log transport is visible in the dashboard

The Dashboard recent requests table SHALL display each row's recorded request transport so operators can distinguish websocket and HTTP proxy traffic without leaving the UI. The table SHALL remain renderable for legacy rows whose transport is missing.

#### Scenario: Websocket request row is visible

- **WHEN** `/api/request-logs` returns a request row with `transport = "websocket"`
- **THEN** the recent requests table shows a visible websocket transport indicator for that row

#### Scenario: Legacy request row without transport still renders

- **WHEN** `/api/request-logs` returns a request row with `transport = null`
- **THEN** the recent requests table still renders the row and shows a neutral placeholder instead of breaking layout

### Requirement: Accounts page

The Accounts page SHALL display a two-column layout: left panel with searchable account list, import button, export button, and add account button; right panel with selected account details including usage, token info, and actions (pause/resume/delete/re-authenticate).

#### Scenario: Account selection

- **WHEN** a user clicks an account in the list
- **THEN** the right panel shows the selected account's details

#### Scenario: Batch account import

- **WHEN** a user clicks the import button and uploads one or more `auth.json` files
- **THEN** the app calls `POST /api/accounts/import/batch`
- **AND** the response reports imported and failed files independently
- **AND** the account list is refreshed when at least one file imports successfully

#### Scenario: Export current auth payload archive

- **WHEN** a user clicks the export button
- **THEN** the app downloads a zip archive containing one current `auth.json` payload per stored account

#### Scenario: Ambiguous duplicate identity import conflict

- **WHEN** `importWithoutOverwrite` was previously enabled and duplicate accounts with the same email exist
- **AND** overwrite mode is enabled again
- **AND** a new import matches multiple existing accounts by email without an exact ID match
- **THEN** `POST /api/accounts/import` returns `409` with `error.code=duplicate_identity_conflict`
- **AND** no existing account is modified

#### Scenario: OAuth add account

- **WHEN** a user clicks the add account button
- **THEN** an OAuth dialog opens with browser and device code flow options

#### Scenario: Account actions

- **WHEN** a user clicks pause/resume/delete on an account
- **THEN** the corresponding API is called and the account list is refreshed
### Requirement: Settings page
The Settings page SHALL include sections for: routing settings (sticky threads, reset priority, prompt-cache affinity TTL), password management (setup/change/remove), TOTP management (setup/disable), API key auth toggle, API key management (table, create, edit, delete, regenerate), and sticky-session administration.

#### Scenario: Save prompt-cache affinity TTL
- **WHEN** a user updates the prompt-cache affinity TTL from the routing settings section
- **THEN** the app calls `PUT /api/settings` with the updated TTL and reflects the saved value

#### Scenario: View sticky-session mappings
- **WHEN** a user opens the sticky-session section on the Settings page
- **THEN** the app fetches sticky-session entries and displays each mapping's kind, account, timestamps, and stale/expiry state

#### Scenario: Purge stale prompt-cache mappings
- **WHEN** a user requests a stale purge from the sticky-session section
- **THEN** the app calls the sticky-session purge API and refreshes the list afterward
