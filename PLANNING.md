# PLANNING.md — rdo_googlebot

## Status

| Phase | Status | Blocker |
|---|---|---|
| 1 — CLI Demo | ✅ Complete | — |
| 2 — Apps Script | ⏸️ Blocked | Node.js/clasp from IT |
| 3 — Cloud Run | ⏸️ Blocked | GCP billing on `pipeline-bot-488915` |

---

## Phase 1 — CLI Demo ✅

**Complete. Core modules fully functional.**

### Core Functionality
- `core/parser.py` — message parsing (codes, mentions, notes, tractor URLs, 📝 flag, info subcommand)
- `core/shotgrid.py` — ShotGrid REST client (Shot → Asset → Version fallback, asset info with publishes)
- `core/formatter.py` — reply formatting (single/multi-code, per-code notes, shared notes, asset info with warnings)
- `bots/sgbot.py` — main bot logic
- `bot_simulate.py` — single message CLI test
- `bot_interactive.py` — continuous mode CLI test
- `bot_post.py` — manual webhook sender (updated to multi-code)

### Recent Enhancements (March 2026)
- ✅ Multi-code API consistency (all scripts use `parseAllCodes`)
- ✅ `/sg info <assetCode>` subcommand
- ✅ Publish-based status (uses `asset_resolver.py`)
- ✅ Version mismatch warnings (Model vs Rig, Texture vs Shading)
- ✅ Approval/Push summaries
- ✅ Asset review status display

---

## Phase 2 — Apps Script ⏸️

**Blocked.** `onMessage` trigger receives null event — known Google Workspace domain bug.
Requires Node.js + clasp in rez. IT request submitted.

---

## Phase 3 — Cloud Run ⏸️

**Blocked.** GCP billing not enabled on `pipeline-bot-488915`.
IT request submitted. Once approved:

- [ ] FastAPI wrapper around Phase 1 bot logic
- [ ] Dockerfile (bundle Python scripts from http://mtl-webapps01/sg_dependencies/)
- [ ] Deploy to Cloud Run
- [ ] Register HTTPS endpoint in Google Cloud Console
- [ ] Bot goes fully automatic

**Deployment Strategy:**
- Bundle `asset_resolver.py` and `sg_core.py` from http://mtl-webapps01/sg_dependencies/ in Docker image
- Include all dependencies in Dockerfile (cannot access internal HTTP server from Cloud Run)
- Phase 1 local testing uses direct path to webapps server scripts

---

## Sprint — Daily Dependencies Feature

**Status:** Planned

### Goal
Add `/sg deps <code>` subcommand to list daily dependencies through the chatbot.

### Requirements
- [ ] Query ShotGrid for upstream/downstream dependencies
- [ ] Support Shot and Asset dependency queries
- [ ] Format dependency tree in readable format
- [ ] Show dependency status (blocked, ready, complete)
- [ ] Handle circular dependencies gracefully
- [ ] Add to parser.py as new subcommand
- [ ] Update formatters for dependency output
- [ ] Test with real production data

### Use Cases
- Coordinator checks what's blocking a shot: `/sg deps 306dtt_1440`
- Check what depends on an asset: `/sg deps chrNolmen`
- Daily standup dependency review

---

## Next Up (when unblocked)

### Google Tasks Integration

New file: `core/tasks.py`

```python
getOrCreateTaskList(listName)   # find or create "sgbot" list, cache ID
createSpaceTask(code, note, sgLink, assignee)  # create task, fail silently
```

- OAuth 2.0 — `credentials.json` + `token.json` (both gitignored)
- New file: `auth_setup.py` — one-time browser auth
- Trigger: 📝 emoji in message → `hasTask = True`
- Never block bot reply on Tasks failure
- Add to `requirements.txt`: `google-auth-oauthlib`, `google-auth-httplib2`, `google-api-python-client`

**Setup order:**
1. Enable Google Tasks API in `pipeline-bot-488915`
2. Create OAuth 2.0 Desktop app credentials → download as `credentials.json`
3. `rez env python-3.11.9 -- python auth_setup.py`
4. Authorize in browser → `token.json` saved

---

## Architecture (Target — Phase 3)

```
User types in Space
  → Google Chat
  → POST https://<cloud-run-url>/bot/sg
  → FastAPI
  → ShotGrid REST API
  → formatted reply
  → Space (in-thread)
```

## Architecture (Current — Phase 1)

```
Paste raw Space message
  → bot_simulate.py CLI
  → ShotGrid REST API
  → formatted reply
  → terminal + optional Space webhook
```

---

## Key Decisions

| Decision | Choice | Reason |
|---|---|---|
| Command | `/sg` | Short, familiar to coords |
| Task trigger | 📝 emoji | Natural, no new syntax |
| Tasks | opt-in only | Prevents noise |
| ShotGrid | READ-ONLY | No unintended side effects |
| Silent mode | on | Prevents Space flooding |
| @mentions | `@username` string | Webhook can't do clickable mentions |
| One Space = one show | yes | No show code needed in command |

---

## Commit History (March 2026)

```
b02ba76  docs: update README and PLANNING with March 2026 accomplishments
5a29efb  docs: update README with flexible command order and mention limitations
fb50f1c  fix: revert to @username format and add flexible command order
a44e443  feat: add proper Google Chat user mentions
b4f4998  feat: rename /note to /sg and change reply emoji to 📝
```
