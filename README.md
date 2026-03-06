# rdo_googlebot

Internal Rodeo FX pipeline bot for Google Spaces. Queries ShotGrid and posts formatted replies.

## Quick Start

```bash
# Run CLI demo tool
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_simulate.py

# Test with a message
rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_simulate.py "@Louis Paré /sg 306dtt_1440 not seeing the MP in the bg"
```

## Features

- **READ-ONLY** ShotGrid queries (shots, assets, versions)
- Parses Google Space messages (natural format or `/sg` commands)
- Formats bot replies with ShotGrid links and status
- CLI demo tool for testing before Cloud Run deployment

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

### CLI Demo Tool

```bash
# Interactive mode (paste message, Ctrl+D to submit)
python bot_simulate.py

# Direct command
python bot_simulate.py "@Louis Paré /sg 306dtt_1440 not seeing the MP"

# Natural Space message format
python bot_simulate.py "Eileen Bocanegra, 10:41 AM
306dtt_1440 still not seeing the MP in the bg. @Louis Pare"
```

### Example Output

```
============================================================
Processing message...
============================================================

Parsed:
  Tagged: Louis Pare
  Code: 306dtt_1440
  Note: still not seeing the MP in the bg.

Querying ShotGrid for: 306dtt_1440

ShotGrid result:
  Found: True
  Type: Shot
  ID: 228221
  Status: ip

============================================================
Bot reply:
============================================================
✅ Message recorded

@Louis Pare — please check 306dtt_1440
"still not seeing the MP in the bg."

Shot status: ip
→ ShotGrid: https://rodeofx.shotgrid.autodesk.com/detail/Shot/228221
Ticket sent to CG Dashboard
============================================================
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

## Message Parsing

The bot supports two message formats:

### Format 1: `/sg` Command
```
@Louis Paré /sg 306dtt_1440 not seeing the MP in the bg
```

### Format 2: Natural Space Message
```
Eileen Bocanegra, 10:41 AM
306dtt_1440 still not seeing the MP in the bg. @Louis Pare
```

Both formats extract:
- **Tagged user**: Who is being asked (`@Louis Paré`)
- **Code**: Shot/asset code (`306dtt_1440`)
- **Note**: Message text (`not seeing the MP in the bg`)

## ShotGrid Lookup Logic

1. Try **Shot** (code contains query)
2. Try **Asset** (code contains query)
3. Try **Version** (numeric ID)

Returns: found, type, id, code, status, link

## Reply Format

```
✅ Message recorded

@User — please check CODE
"note text"

Shot status: STATUS
→ ShotGrid: LINK
Ticket sent to CG Dashboard
```

Pipeline issues shown only if detected (`isOutOfDate = true`).

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

### "No shot/asset code found"
- Message must contain shot code pattern: `###xxx_####` (e.g., `306dtt_1440`)
- Or use `/sg CODE` command format

### "Not found in ShotGrid"
- Code doesn't match any Shot, Asset, or Version
- Check spelling and verify entity exists in ShotGrid

## License

Internal Rodeo FX tool. Not for external distribution.
