# Lessons

## 2026-03-07
- When a failing test contradicts an explicit product-policy comment from the user or code owner, treat the test as stale first and verify intent before changing production behavior.
- For policy-driven behavior toggles or allowlists, prefer the narrowest code change and revisit the test contract before expanding runtime effects.

## 2026-03-09
- When adding a new authentication header, confirm whether it is `alternative` auth or an `additional` auth gate before implementation; default to preserving existing auth semantics unless explicitly told to replace them.
