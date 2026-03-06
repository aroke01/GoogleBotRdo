# CLAUDE.md — rdo_googlebot

Paste this file in your project root. Claude Code reads it automatically on startup.

---

## Project
`rdo_googlebot` — Internal Rodeo FX pipeline bot for Google Spaces.
Queries ShotGrid and posts formatted replies in Google Chat spaces.

## Stack
- Python 3.11.9
- ShotGrid REST API (`https://rodeofx.shotgrid.autodesk.com`)
- Google Chat outgoing webhook
- Apps Script (interim) / Cloud Run FastAPI (target)
- Rez for environment management

## Run command
```bash
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 requests -- python <script.py>
```


IMPORTANT: DO NOT WRITE ANYTHING to Shotgrid. 


## Credentials
ShotGrid credentials are in `api.key` (gitignored).
Load via:
```python
from core.shotgrid import getSgToken
```
Never hardcode credentials. Never commit api.key.

## ShotGrid Auth
Script-based auth. Uses `SG_SCRIPT_NAME` + `SG_SCRIPT_KEY` from `api.key`.
REST API endpoint: `https://rodeofx.shotgrid.autodesk.com/api/v1/`
Token endpoint: `/api/v1/auth/access_token` with `grant_type=client_credentials`

## Google Space Webhook
Outgoing webhook URL is in `api.key` as `SPACE_WEBHOOK`.
POST JSON `{"text": "..."}` to send a message to the Space.

## Coding conventions
- camelCase for functions and variables
- Google-style docstrings
- Absolute imports
- Reuse existing functions, do not rewrite what exists
- No trailing whitespace

## Current files
- `bot_reply.py` — sends a message to Google Space via webhook (working)
- `bot_simulate.py` — CLI demo: paste Space message, get formatted reply (in progress)
- `core/shotgrid.py` — ShotGrid REST client (token, search)
- `core/parser.py` — extracts @mention, shot/asset code, note from raw message
- `core/formatter.py` — formats bot reply string
- `bots/sgbot.py` — main bot logic, reusable for Cloud Run

## Key behaviors
- One Space = one show (lbp3). Never ask for show code.
- Bot is READ-ONLY. Never write to ShotGrid.
- Reply format: acknowledge + tag person + ShotGrid link
- Show pipeline issues ONLY if detected (isOutOfDate = true)
- Keep replies short — coords want confirmation, not pipeline details

## ShotGrid lookup logic
1. Try shot (code contains query)
2. Try asset (code contains query)
3. Try version by numeric ID
Returns: found, type, id, code, status, link

## Example Space message to parse
```
Eileen Bocanegra, 10:41 AM
306dtt_1440 still not seeing the MP in the bg. @Louis Pare
```

## Expected bot reply
```
✅ Message recorded

@Louis Paré — please check 306dtt_1440
"not seeing the MP in the bg"

→ ShotGrid
Ticket sent to CG Dashboard
```

## Current blocker
`onMessage` trigger in Apps Script receives empty event.
Workaround: manual `bot_reply.py` for demos.
Fix path: Cloud Run (needs GCP billing on `pipeline-bot-488915`).

## Do not
- Do not modify `api.key`
- Do not write to ShotGrid
- Do not add dependencies outside the rez environment
- Do not use async (not needed, rez Python is sync)
