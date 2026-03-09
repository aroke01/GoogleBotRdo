# Task: Add getAssetInfo() to core/shotgrid.py

## Before writing anything
1. Read CLAUDE.md
2. Read core/shotgrid.py in full
3. Read core/formatter.py in full
4. Do not create new files

---

## ADD: getAssetInfo(sg, assetCode)

Add to core/shotgrid.py.

### ShotGrid query — Asset

Find asset where `code` contains `assetCode`.
Fields to fetch:
- code
- sg_status_list
- sg_asset_type
- sg_stage (field name: stage)
- id

### ShotGrid query — Tasks

For the asset found above, query Task entities:
- Filter: entity is the asset, step.name ends with "(A)"
- Fields: content, sg_status_list, task_assignees, step.name, updated_at
- Steps to include: "Modeling (A)", "Texturing (A)", "Shading (A)", "Rigging (A)"
- Per step: keep only the task with the latest updated_at
- From that task: take sg_status_list and all task_assignees names

### Return dict

```python
{
    "found": True,
    "code": "chrNolmen",
    "type": "Character",
    "status": "ip",
    "stage": "Active",
    "sg_url": "https://rodeofx.shotgrid.autodesk.com/page/1434867",
    "tasks": {
        "Modeling": {"status": "apr", "assignees": ["Daniel Lupien"]},
        "Texturing": {"status": "apr", "assignees": ["Valerie Lover"]},
        "Shading":   {"status": "ip",  "assignees": ["Gabriel Trudeau"]},
        "Rigging":   {"status": "ip",  "assignees": ["Vincent Desjardins", "Hannes Faupel"]},
    }
}
```

If asset not found, return:
```python
{"found": False, "code": assetCode}
```

Strip " (A)" suffix from step name before using as dict key.

---

## ADD: formatAssetInfo(assetData) in core/formatter.py

Read formatter.py before writing. Add after existing functions.

Status emoji map:
```
ip   → 🔄
new  → ⬜
lck  → 🔒
psh  → 📤
apr  → ✅
omt  → ➖
void → 🚫
del  → 🗑️
rev  → 👁️
```

Output format:
```
📋 chrNolmen — Character · Active

Modeling   apr ✅  Daniel Lupien
Texturing  apr ✅  Valerie Lover
Shading    ip  🔄  Gabriel Trudeau
Rigging    ip  🔄  Vincent Desjardins, Hannes Faupel

🔗 ShotGrid
```

- Dept column: left-aligned, padded to longest name
- Status code: 4 chars, left-aligned
- Emoji after status code
- Assignees: comma-separated on same line
- If no assignee: show `—`
- If dept has no task: skip that dept entirely
- ShotGrid link on last line using sg_url

---

## ADD: handle `info` subcommand in bots/sgbot.py

Read sgbot.py before writing.

If parsed message contains subcommand `info` and at least one code:
- Call getAssetInfo(sg, code)
- If found: call formatAssetInfo(result), post reply
- If not found: reply "❓ chrNolmen — not found in ShotGrid"

Subcommand detection in parser.py:
- If message contains `/sg info <code>` → set parsed["subcommand"] = "info"
- Code is the token immediately after `info`

---

## Coding conventions
- camelCase functions and variables
- Google-style docstrings
- Absolute imports
- No type hints
- Reuse existing functions — do not duplicate
- No trailing whitespace
- Update __init__.py exports if new public functions added
- Confirm on main branch before committing
