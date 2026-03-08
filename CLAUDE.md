# CLAUDE.md — rdo_googlebot

Internal Rodeo FX pipeline bot for Google Spaces.
Queries ShotGrid and posts formatted replies.

---

## Project

- **Repo:** rdo_googlebot
- **Branch:** always `main` (never master)
- **Push:** `git push origin main` — server auto-deploys on push

## Google Cloud

- **Project:** Rdo Shotgrid Bot
- **ID:** `pipeline-bot-488915`
- **Number:** `420693039096`
- **Chat API:** enabled
- **Bot name:** sgbot
- **Space webhook:** stored in `api.key` (gitignored)

## Rez Run

```bash
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_simulate.py
```

## Project Structure

```
rdo_googlebot/
├── bot_simulate.py          # CLI demo — single message
├── bot_interactive.py       # CLI demo — continuous mode
├── bot_reply.py             # Manual webhook sender
├── core/
│   ├── __init__.py
│   ├── parser.py            # Message parsing
│   ├── shotgrid.py          # ShotGrid REST client
│   └── formatter.py         # Reply formatting
├── bots/
│   ├── __init__.py
│   └── sgbot.py             # Main bot logic
├── Python/
│   └── sg_auth.py           # 5-tier auth fallback
├── api.key                  # Gitignored
└── test_sg_access.py
```

## api.key Format

```
SG_URL=https://rodeofx.shotgrid.autodesk.com
SG_SCRIPT_NAME=shell
SG_SCRIPT_KEY=your_api_key_here
SPACE_WEBHOOK=https://chat.googleapis.com/...
```

Never commit `api.key`, `token.json`, or `credentials.json`.

---

## Coding Conventions (strict)

- **camelCase** for all functions, variables, class attributes — intentional for Python
- **Google-style docstrings** on every function and module
- **Absolute imports** only
- **PEP8 import order:** stdlib → third-party → local
- **snake_case** for file and directory names
- No type hints unless explicitly requested
- No trailing whitespace
- No single-character names (vars, functions, loops, classes)
- No `getattr` or other defensive patterns
- `try/except` must catch a specific exception — never bare
- Smallest possible code; reuse before adding
- One clear responsibility per function (stated in docstring)
- When adding a module: update `__init__.py` exports
- Before committing: `git branch` to confirm on `main`
- If intent is unclear: ask or leave a TODO, never guess
- Do not rename existing symbols unless explicitly instructed
- Do not change existing behavior unless explicitly instructed
- Bump `APP_VERSION` when changes require restart
- Update `README.md` when commands change

---

## ShotGrid

- **READ-ONLY** — bot never writes to ShotGrid
- Auth: 5-tier fallback in `Python/sg_auth.py`
- Lookup order: Shot → Asset → Version (by numeric ID)
- Returns: `found`, `type`, `id`, `code`, `status`, `sg_url`

---

## Bot Behavior

**Trigger conditions (ALL required):**
1. Message contains `/sg`
2. Message contains at least one `@mention`
3. At least one valid ShotGrid code found

**Silent mode:** bot ignores messages without `/sg` — prevents flooding.

**Command order:** flexible — both work:
```
@lpare /sg 306dtt_1000 check this
/sg @lpare 306dtt_1000 check this
```

**Task flag:** if message contains 📝 emoji → create Google Task (opt-in).
Strip 📝 from note text before formatting reply.

---

## Supported Code Patterns

| Type | Example |
|---|---|
| Shot | `306dtt_1440` |
| Asset | `chrNolmen`, `prpSphere` |
| Version | `306dtt_1980.qcani.primary.main.defPart.v13` |
| Version ID | `ID: 4367413` or bare 7-digit number |
| Tractor URL | `http://tractor/tv/#jid=4448933` |

---

## Reply Format

**Single code:**
```
📝 recorded: to @lpare - Please check 306dtt_1000, check the qc please → ShotGrid
```

**Multi-code:**
```
📝 Recorded — N items
@lpare — please check:
- 306dtt_1000 → ShotGrid (check qc)
- chrNolmen → ShotGrid (rig broken)
```

**With task flag (📝 in message):**
```
📝 Recorded — N items
@lpare — please check:
- 306dtt_1000 → ShotGrid (check qc)
📝 Task created
```

**Unknown code:**
```
- prpUnknown → ❓ not found in ShotGrid (note)
```

---

## Google Tasks (planned)

- OAuth 2.0 — `credentials.json` (Desktop app) + `token.json`
- Task list: `sgbot`
- Title: `Check {code} — {note}`
- Tasks API failures: silent, never block bot reply
- One-time setup: `python auth_setup.py`

---

## Deployment Phases

| Phase | Status | Blocker |
|---|---|---|
| 1 — CLI Demo | ✅ Complete | — |
| 2 — Apps Script | ⏸️ Blocked | Node.js/clasp approval from IT |
| 3 — Cloud Run | ⏸️ Blocked | GCP billing on `pipeline-bot-488915` |

---

## Key Constraints

- One Space = one show (`lbp3`) — no show code needed
- Coordinators don't change habits — bot integrates into existing workflow
- Webhook limitation: cannot create clickable @mentions without numeric Google user IDs
- Replies use `@username` format (readable, no notification ping)
