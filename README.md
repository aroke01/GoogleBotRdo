# rdo_googlebot

Internal Rodeo FX pipeline bot for Google Spaces. Queries ShotGrid and posts formatted replies with **multi-code support**.

## Quick Start

```bash
# Run CLI demo tool
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_simulate.py

# Test with multiple codes
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_simulate.py "@lpare /sg 306dtt_1000 check qc, chrNolmen rig broken"

# Interactive mode
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_interactive.py
```

## Features

- **Multi-code support** - Handle multiple shots/assets in one message
- **Per-code notes** - Attach individual notes to each code
- **Silent mode** - Only responds to `/sg` commands (prevents flooding)
- **Unknown codes shown** - Displays codes not found in ShotGrid
- **READ-ONLY** ShotGrid queries (shots, assets, versions)
- **Tractor log URLs** - Automatically detects and includes Tractor links
- CLI demo tools for testing before Cloud Run deployment

## Project Structure

```
rdo_googlebot/
├── bot_simulate.py          # CLI demo tool (main entry point)
├── core/
│   ├── parser.py            # Message parsing (@mentions, codes, notes)
│   ├── shotgrid.py          # ShotGrid REST queries
│   └── formatter.py         # Reply formatting
├── bots/
│   └── sgbot.py             # Main bot logic (reusable for Cloud Run)
├── Python/
│   └── sg_auth.py           # ShotGrid authentication (5-tier fallback)
├── api.key                  # ShotGrid credentials (gitignored)
└── test_sg_access.py        # ShotGrid API connection test
```

## Usage Examples

### CLI Demo Tool (bot_simulate.py)

```bash
# Interactive mode (paste message, Ctrl+D to submit)
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_simulate.py

# Single code
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_simulate.py "@lpare /sg 306dtt_1440 check qc"

# Multiple codes with per-code notes
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_simulate.py "@lpare /sg 306dtt_1000 check qc, chrNolmen rig broken"

# Multiple codes with shared note
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_simulate.py "@lpare /sg 306dtt_1000 518dvd_4300 both have cache issues"
```

### Interactive Mode (bot_interactive.py)

```bash
# Start interactive mode - paste messages and get instant replies
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_interactive.py
```

### Example Output (Multi-Code)

```
============================================================
Processing message...
============================================================

Parsed:
  @mentions: lpare, john
  Codes found: 2

Querying ShotGrid...
  ✓ 306dtt_1000 — Shot (status: ip)
  ✓ chrNolmen — Asset (status: cmpt)

============================================================
Bot reply (posting to Space):
============================================================
📝 Recorded — 2 items
@lpare @john — please check:
- 306dtt_1000 → ShotGrid (check qc)
- chrNolmen → ShotGrid (rig broken)
============================================================

✓ Posted to Space (HTTP 200)
```

## Configuration

### ShotGrid Credentials

Create `api.key` file in project root:

```
SG_URL=https://rodeofx.shotgrid.autodesk.com
SG_SCRIPT_NAME=shell
SG_SCRIPT_KEY=your_api_key_here
```

**Never commit `api.key` to git.**

### Authentication Fallback

The bot uses a 5-tier authentication system:

1. Environment variables (`SHOTGRID_SCRIPT_NAME`, `SHOTGRID_API_KEY`)
2. `api.key` file (recommended)
3. `rdo_shotgun_core` module (Rez environment)
4. Command line arguments
5. Error with helpful message

## Testing

```bash
# Test ShotGrid API connection
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python test_sg_access.py

# Test bot with sample messages
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_simulate.py "@User /sg 001_wag010 test note"
```

## Message Formats

### Single Code with Note
```
@lpare /sg 306dtt_1000 check the qc please
```
**Reply:**
```
📝 recorded: to lpare - Please check 306dtt_1000, check the qc please → ShotGrid
```

### Multiple Codes with Per-Code Notes (Comma-Separated)
```
@lpare /sg 306dtt_1000 check qc, chrNolmen rig broken, 305dtt_0200 cache issues
```
**Reply:**
```
📝 Recorded — 3 items
@lpare — please check:
- 306dtt_1000 → ShotGrid (check qc)
- chrNolmen → ShotGrid (rig broken)
- 305dtt_0200 Unknown shot/asset (cache issues)
```

### Multiple Codes with Shared Note (Space-Separated)
```
@lpare /sg 306dtt_1000 518dvd_4300 both have cache issues
```
**Reply:**
```
📝 Recorded — 2 items
@lpare — please check:
- 306dtt_1000 → ShotGrid
- 518dvd_4300 → ShotGrid
Note: both have cache issues
```

### Multiple @mentions
```
@lpare @john /sg 306dtt_1000 check this, chrNolmen review rig
```
**Reply:**
```
📝 Recorded — 2 items
@lpare @john — please check:
- 306dtt_1000 → ShotGrid (check this)
- chrNolmen → ShotGrid (review rig)
```

### With Tractor Log URL
```
@lpare /sg 306dtt_1000 failed render, see http://tractor/tv/#jid=4448933
```
**Reply:**
```
📝 Recorded — 2 items
@lpare — please check:
- 306dtt_1000 → ShotGrid (failed render)
- Tractor log: http://tractor/tv/#jid=4448933
```

### Silent Mode (No /sg Command)
```
test
```
**Reply:** *(stays silent, no message posted)*

```
@lpare 306dtt_1000 has issues
```
**Reply:** *(stays silent, requires /sg command)*

## ShotGrid Lookup Logic

1. Try **Shot** (code contains query)
2. Try **Asset** (code contains query)
3. Try **Version** (numeric ID)

Returns: found, type, id, code, status, link

## Supported Code Patterns

- **Shot codes:** `306dtt_1440`, `518dvd_4300` (3 digits + 3 letters + underscore + 4 digits)
- **Asset codes:** `chrNolmen`, `setWarehouse` (3 lowercase + capital + rest)
- **Version codes:** `306dtt_1980.qcani.primary.main.defPart.v13`
- **Version IDs:** `ID: 4367413` or bare 7-digit numbers
- **Tractor URLs:** `http://tractor/tv/#jid=4448933`

## Coding Conventions

- **camelCase** for functions and variables (intentional for Python)
- **Google-style docstrings** for all functions
- **Absolute imports** only
- **No type hints** (unless explicitly requested)
- **snake_case** for file/directory names
- Reuse existing code, avoid duplication

## Deployment Roadmap

### Phase 1: CLI Demo ✅ (Current)
- ✅ Core modules (`parser`, `shotgrid`, `formatter`)
- ✅ Bot logic (`bots/sgbot.py`)
- ✅ CLI tool (`bot_simulate.py`)
- ✅ ShotGrid API access verified

### Phase 2: Apps Script (if clasp approved)
- [ ] `clasp push` workflow
- [ ] Fix `onMessage` trigger

### Phase 3: Cloud Run (when GCP billing approved)
- [ ] FastAPI app wrapping Phase 1 logic
- [ ] Dockerfile
- [ ] Deploy to Cloud Run
- [ ] Register HTTPS endpoint
- [ ] Bot goes fully automatic

## Important Notes

- **One Space = one show** (lbp3). Show code never needed in command.
- **READ-ONLY** — bot never writes to ShotGrid.
- Coordinators don't change habits — bot integrates into existing workflow.
- Keep replies short — coords want confirmation, not pipeline details.

## Troubleshooting

### "Can't authenticate script"
- Check `api.key` has correct `SG_SCRIPT_NAME` and `SG_SCRIPT_KEY`
- Script name should match ShotGrid API script (e.g., `shell`)

### Bot Stays Silent
- Message must contain `/sg` command to trigger bot
- Message must contain at least one `@mention`
- This prevents flooding the Space with error messages

**Note:** The 📝 emoji in bot replies prepares for future webapps-based ticket system integration.

### "Not found in ShotGrid"
- Code doesn't match any Shot, Asset, or Version
- Check spelling and verify entity exists in ShotGrid

## License

Internal Rodeo FX tool. Not for external distribution.
