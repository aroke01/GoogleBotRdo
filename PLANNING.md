# rdo_googlebot — Planning

## Goal
Command-line Python tool that simulates the Google Spaces bot experience.
A coordinator pastes a real Space message, the tool parses it, queries ShotGrid,
and prints a formatted bot reply — exactly what sgbot will post when live.

---

## Accomplishments (March 2026)

### ✅ Phase 1 Complete — CLI Demo Tools
- **Command renamed:** `/note` → `/sg` for shorter syntax
- **Reply emoji:** Changed from ✅ to 📝 (preparing for future ticket system)
- **Flexible parsing:** Accepts both `@user /sg code` and `/sg @user code` order
- **Multi-code support:** Handle multiple shots/assets in one message with per-code notes
- **Interactive mode:** `bot_interactive.py` for real-time testing
- **Simulation mode:** `bot_simulate.py` for batch testing
- **User mentions:** Bot replies with `@username` format (webhook limitation documented)

### 🔧 Technical Improvements
- Modular architecture: `core/parser.py`, `core/formatter.py`, `core/shotgrid.py`
- Comprehensive regex patterns for shot codes, asset codes, version IDs
- Tractor URL detection and inclusion in replies
- Silent mode: only responds when `/sg` command + @mention present
- Unknown codes displayed in replies instead of staying silent

---

## Current State
- ShotGrid REST API: ✅ working (auth, shot/asset/version lookup)
- Google Space webhook (outgoing): ✅ working
- CLI demo tools: ✅ fully functional
- Multi-code parsing: ✅ working
- Flexible command order: ✅ working
- Incoming trigger (onMessage): ⏸️ blocked — needs HTTPS or Cloud Run
- Demo tool (bot_reply.py): ✅ enhanced and working

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

### Phase 1 — CLI Demo ✅ COMPLETE
- [x] Refactor bot_reply.py into core/ modules
- [x] Build bot_simulate.py — paste message, get formatted reply
- [x] Build bot_interactive.py — real-time testing mode
- [x] Test with real Space messages from coordinators
- [x] Nail the reply format (📝 emoji, @mentions, multi-code support)
- [x] Rename command from `/note` to `/sg`
- [x] Add flexible command order parsing
- [x] Document webhook limitations

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
# Run simulation mode (single message test)
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_simulate.py "@lpare /sg 306dtt_1440 check cache"

# Run interactive mode (continuous testing)
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_interactive.py

# Test with multiple codes
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_simulate.py "@lpare /sg 306dtt_1000 check qc, chrNolmen rig broken"

# Both command orders work
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_simulate.py "@lpare /sg 306dtt_1440 test"
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_simulate.py "/sg @lpare 306dtt_1440 test"
```

---

## Notes
- One Space = one show (lbp3). Show code never needed in command.
- Bot replies are read-only — nothing writes to ShotGrid.
- Reply format: acknowledge + tag person + ShotGrid link. Pipeline details only if issues detected.
- Coords don't change habits — bot integrates into existing Space workflow.
