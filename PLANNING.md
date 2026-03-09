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
- `core/parser.py` — message parsing (codes, mentions, notes, tractor URLs, 📝 flag, info/deps subcommands)
- `core/shotgrid.py` — ShotGrid REST client (Shot → Asset → Version fallback, asset info with publishes, dependency tree)
- `core/formatter.py` — reply formatting (single/multi-code, per-code notes, shared notes, asset info with warnings, dependency tree ASCII art)
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
- ✅ `/sg dep|deps|dependency|dependencies <code>` subcommand - daily dependency tree (version ID, version code, or shot code)

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

**Status:** ✅ Complete (March 2026)

### Goal
Add `/sg deps <code>` subcommand to list daily dependencies through the chatbot.

### Requirements
- [x] Query ShotGrid for upstream/downstream dependencies
- [x] Support Version ID, Version code, and Shot code inputs
- [x] Format dependency tree in readable ASCII art format
- [x] Show department labels and version numbers
- [x] Display QC versions alongside regular dailies
- [x] Add to parser.py as new subcommand
- [x] Update formatters for dependency output
- [x] Test with real production data

### Implementation
Command variations (all accepted):
- `/sg dep <code>` - short form
- `/sg deps <code>` - short plural
- `/sg dependency <code>` - full word
- `/sg dependencies <code>` - full word plural

Input types:
- `/sg dep 4510266` (version ID)
- `/sg dep 313lhb_2840.qcani.primary.main.defPart.v1` (version code)
- `/sg dep 313lhb_2840` (shot code - finds latest version)

### Output Format
```
🔗 Dependencies for 313lhb_2840.qcani.primary.main.defPart.v1

└── (Anim QC, v1) 313lhb_2840.qcani.primary.main.defPart.v1
    └── (Layout, v1) 313lhb_2840.lay.witnessCam.v1 <---> QC
        └── (CMM, v002) 313lhb_2840_bg01_cmm_v002
            └── (Editorial, v1) 313lhb_2840.lineup.autoLineup.v1
                └── (Plate, v1) 313lhb_2840.ingest.cc01.rdo-nwb.distort.compPlate.v1

🔗 ShotGrid
```

### Use Cases
- Coordinator checks what's blocking a shot: `/sg deps 306dtt_1440` ✓
- Check dependencies for a specific daily: `/sg deps 4510266` ✓
- Understand full pipeline chain for review

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
