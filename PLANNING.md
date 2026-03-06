# rdo_googlebot — Planning

## Goal
Command-line Python tool that simulates the Google Spaces bot experience.
A coordinator pastes a real Space message, the tool parses it, queries ShotGrid,
and prints a formatted bot reply — exactly what sgbot will post when live.

---

## Current State
- ShotGrid REST API: working (auth, shot/asset/version lookup)
- Google Space webhook (outgoing): working
- Incoming trigger (onMessage): blocked — needs HTTPS or Cloud Run
- Demo tool (bot_reply.py): working but basic

---

## Blockers
- **HTTPS** — Google Chat requires HTTPS to POST incoming messages to our server
- **GCP Billing** — needed for Cloud Run (Plan A)
- **Node.js / clasp** — needed for Apps Script CLI iteration (Plan B)

IT request sent. Waiting on Plan A (GCP billing on `pipeline-bot-488915`).

---

## Architecture (target)

```
User types in Space
       ↓
Google Chat → POST https://our-cloud-run-url/bot/sg
       ↓
FastAPI app (Cloud Run)
       ↓
ShotGrid REST API
       ↓
Formatted reply → Space
```

## Architecture (demo / interim)

```
Paste raw Space message into CLI
       ↓
bot_simulate.py parses message
       ↓
ShotGrid REST API
       ↓
Formatted reply printed to terminal
       ↓
(optional) posted to Space via webhook
```

---

## Demo Tool — bot_simulate.py

### Input
Raw Google Space message pasted as string. Example:

```
Eileen Bocanegra, 10:41 AM
Hello! Got a flag in anim vfx dailies from Ara that in 306dtt_1440 we are
still not seeing the MP in the bg it was the cg background still.
Who do we ask to help us update the bg with the mp? @Louis Pare
```

### What it does
1. Extracts @mention (who is being asked)
2. Extracts shot/asset code (306dtt_1440)
3. Queries ShotGrid for shot status + pipeline issues
4. Formats a clean bot reply
5. Prints reply to terminal
6. Optionally posts to Space via webhook

### Output (example)
```
✅ Message recorded

@Louis Paré — please check 306dtt_1440
"not seeing the MP in the bg, still showing CG background"

Shot status: In Progress
Department: Anim / VFX

→ ShotGrid
Ticket sent to CG Dashboard
```

---

## File Structure

```
rdo_googlebot/
├── PLANNING.md              ← this file
├── CLAUDE.md                ← Claude Code context
├── bot_simulate.py          ← CLI demo tool
├── bot_reply.py             ← existing webhook sender
├── core/
│   ├── shotgrid.py          ← ShotGrid REST client
│   ├── parser.py            ← message parsing
│   └── formatter.py         ← reply formatting
├── bots/
│   └── sgbot.py             ← bot logic (reusable for Cloud Run)
├── api.key                  ← ShotGrid credentials (gitignored)
└── requirements.txt
```

---

## Phases

### Phase 1 — CLI Demo (now, no IT needed)
- [ ] Refactor bot_reply.py into core/ modules
- [ ] Build bot_simulate.py — paste message, get formatted reply
- [ ] Test with real Space messages from coordinators
- [ ] Nail the reply format

### Phase 2 — Apps Script (if clasp approved)
- [ ] clasp push workflow
- [ ] Claude Code iteration loop
- [ ] Fix onMessage trigger

### Phase 3 — Cloud Run (when billing approved)
- [ ] FastAPI app wrapping Phase 1 logic
- [ ] Dockerfile
- [ ] Deploy to Cloud Run
- [ ] Register HTTPS endpoint in Google Cloud Console
- [ ] Bot goes fully automatic

---

## Commands

```bash
# Run with rez
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 requests -- python bot_simulate.py

# Test with a real message
python bot_simulate.py "Eileen Bocanegra 10:41 AM: 306dtt_1440 still not seeing the MP @Louis Pare"

# Post to Space
python bot_reply.py "@Louis Paré /sg 306dtt_1440 not seeing MP in bg"
```

---

## Notes
- One Space = one show (lbp3). Show code never needed in command.
- Bot replies are read-only — nothing writes to ShotGrid.
- Reply format: acknowledge + tag person + ShotGrid link. Pipeline details only if issues detected.
- Coords don't change habits — bot integrates into existing Space workflow.
