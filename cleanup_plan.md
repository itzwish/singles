# Cleanup Plan (no edits yet)

## Identified issues

### Fixed

1. WebSocket reconnect is now scheduled from `onclose`; the ref is not cleared until reconnect gives up, so unexpected disconnects recover automatically.
2. `sendMessage()` guards against the race where `ws.value` becomes null during reconnect.
3. Admin chat-log filtering is now wired to the search inputs and filters by text/user/character/role.
4. Admin chat-log pagination now uses `chatLogs` page state (`chatLogPage`, `chatLogPageSize`) and hits the paginated endpoint.
5. `chat_messages` audit rows are drained on backend shutdown via `lifespan`.
6. Audit drop paths now warn instead of only debugging.
7. Admin user table now accepts `premium` and renders a `Premium` chip.

### Still open / verify next

- Confirm the backend admin endpoints used by the admin page (`/admin/chat-logs`, `/admin/stats`, `/admin/users`, `/admin/settings`) exist and return the shapes the frontend now expects. If any are missing, add them next.
- Verify the WebSocket reconnect behaviour live by killing/restarting the backend mid-chat.
- If the admin page still throws runtime Vue errors, check the computed names referenced in the template against the script (`search`, `filteredLogs`, `chatLogPage`, `chatLogPageSize`, `prevPage`, `nextPage`, `applyFilter`, `onSearchDebounce`).
- Confirm `app/api/v1/admin.py` now accepts `premium` for `membership_tier` patch (fixed).
- Confirm `app/main.py` now drains chat audit on shutdown (fixed).
- Confirm `app/services/chat_audit.py` warns on dropped rows and uses per-row `add` (fixed).

Verified so far:
- Frontend production build passes (`vue-tsc` + `vite build`).
- Backend files compile cleanly with the project Python (`py_compile` on `admin.py`, `chat_audit.py`, `main.py`).

### Out of scope unless user asks

- Backend AI fallback and quota behaviour are complex and mostly defensive already; not changing unless there is a specific failure mode to fix.
- Clerk webhook sync is already fairly complete; will not refactor without a concrete bug.
