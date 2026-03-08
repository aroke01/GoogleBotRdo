"""
Reply formatter for rdo_googlebot.

Formats bot replies for Google Spaces with ShotGrid links and status info.
"""


def formatReply(taggedName, code, note, sgData, senderName=None):
    """Format bot reply for Google Space (single line, plain text).
    
    Format: 📝 recorded: from SENDER to RECIPIENT - Please check CODE, NOTE → ShotGrid
    
    Args:
        taggedName: Name of @mentioned user or None
        code: Shot/asset code
        note: Note text from message
        sgData: ShotGrid lookup result dict
        senderName: Name of message sender (optional, for Cloud Run)
        
    Returns:
        str: Formatted reply text (single line)
    """
    if not sgData.get('found'):
        return f"❓ `{code}` — not found in ShotGrid."
    
    parts = ["📝 recorded:"]
    
    if senderName:
        parts.append(f"from {senderName}")
    
    if taggedName:
        parts.append(f"to @{taggedName}")
    
    parts.append("-")
    
    parts.append(f"Please check {code}")
    
    if note:
        parts.append(f", {note}")
    
    sgLink = sgData.get('link')
    if sgLink:
        parts.append(f"→ ShotGrid: {sgLink}")
    else:
        parts.append("→ ShotGrid")
    
    return " ".join(parts)


def formatReplyMarkdown(taggedName, code, note, sgData, senderName=None):
    """Format bot reply with Markdown for Google Space (single line).
    
    Format: 📝 recorded: from SENDER to RECIPIENT - Please check CODE, NOTE → ShotGrid
    
    Args:
        taggedName: Name of @mentioned user or None
        code: Shot/asset code
        note: Note text from message
        sgData: ShotGrid lookup result dict
        senderName: Name of message sender (optional, for Cloud Run)
        
    Returns:
        str: Formatted reply text (single line)
    """
    if not sgData.get('found'):
        return f"❓ `{code}` — not found in ShotGrid."
    
    parts = ["📝 recorded:"]
    
    if senderName:
        parts.append(f"from {senderName}")
    
    if taggedName:
        parts.append(f"to @{taggedName}")
    
    parts.append("-")
    
    parts.append(f"Please check {code}")
    
    if note:
        parts.append(f", {note}")
    
    sgLink = sgData.get('link')
    if sgLink:
        parts.append(f"<{sgLink}|→ ShotGrid>")
    else:
        parts.append("→ ShotGrid")
    
    return " ".join(parts)


def formatMultiCodeReply(taggedNames, validCodeSegments, tractorUrl, invalidCount, sharedNote, useMarkdown=True):
    """Format reply for multiple codes with per-code notes.

    Args:
        taggedNames: List of @mentioned users
        validCodeSegments: List of dicts with 'code', 'note', 'sgLink'
        tractorUrl: Tractor log URL or None
        invalidCount: Number of codes not found in SG
        sharedNote: Shared note text (if no per-code notes)
        useMarkdown: Use Markdown formatting (default: True)

    Returns:
        str: Formatted reply (single or multi-line)
    """
    totalItems = len(validCodeSegments)
    if tractorUrl:
        totalItems += 1

    if totalItems == 0:
        return "❓ No valid codes found in ShotGrid."

    if totalItems == 1 and not tractorUrl and invalidCount == 0:
        segment = validCodeSegments[0]
        code = segment['code']
        note = segment.get('note', '') or sharedNote or ''
        sgLink = segment.get('sgLink')

        taggedStr = ' '.join([f"@{name}" for name in taggedNames]) if taggedNames else ''

        parts = ["📝 recorded:"]
        if taggedStr:
            parts.append(f"to {taggedStr}")
        parts.append("-")
        parts.append(f"Please check {code}")
        if note:
            parts.append(f", {note}")

        if useMarkdown and sgLink:
            parts.append(f"<{sgLink}|→ ShotGrid>")
        elif sgLink:
            parts.append(f"→ ShotGrid: {sgLink}")
        else:
            parts.append("→ ShotGrid")

        return " ".join(parts)

    lines = []
    lines.append(f"📝 Recorded — {totalItems} item{'s' if totalItems > 1 else ''}")

    if taggedNames:
        mentionStr = ' '.join([f"@{name}" for name in taggedNames])
        lines.append(f"{mentionStr} — please check:")
    else:
        lines.append("Please check:")

    for segment in validCodeSegments:
        code = segment['code']
        note = segment.get('note', '')
        sgLink = segment.get('sgLink')

        if useMarkdown and sgLink:
            linkPart = f"<{sgLink}|→ ShotGrid>"
        elif sgLink:
            linkPart = f"→ ShotGrid: {sgLink}"
        else:
            linkPart = "→ ShotGrid"

        if note:
            lines.append(f"- {code} {linkPart} ({note})")
        else:
            lines.append(f"- {code} {linkPart}")

    if tractorUrl:
        if useMarkdown:
            lines.append(f"- <{tractorUrl}|Tractor log: {tractorUrl}>")
        else:
            lines.append(f"- Tractor log: {tractorUrl}")

    if invalidCount > 0:
        lines.append(f"⚠️ {invalidCount} code{'s' if invalidCount > 1 else ''} not found in ShotGrid")

    if sharedNote:
        lines.append(f"Note: {sharedNote}")

    return "\n".join(lines)


def formatAssetInfo(assetData, useMarkdown=True):
    """Format asset info reply with publish breakdown by department.

    Args:
        assetData: Dictionary from getAssetInfo() with asset and publish data
        useMarkdown: Use Markdown formatting for ShotGrid link (default: True)

    Returns:
        str: Formatted multi-line reply with dept version and status
    """
    if not assetData.get('found'):
        code = assetData.get('code', 'unknown')
        return f"❓ {code} — not found in ShotGrid"

    statusEmojiMap = {
        'ip': '🔄',
        'new': '⬜',
        'lck': '🔒',
        'psh': '📤',
        'apr': '✅',
        'cmpt': '✅',
        'omt': '➖',
        'void': '🚫',
        'del': '🗑️',
        'rev': '👁️'
    }

    deptDisplayNames = {
        'model': 'Model',
        'texture': 'Texture',
        'shading': 'Shading',
        'rig': 'Rig',
        'groom': 'Groom'
    }

    code = assetData.get('code', 'unknown')
    assetType = assetData.get('type', 'Unknown')
    stage = assetData.get('stage', 'Unknown')
    sgUrl = assetData.get('sg_url', '')
    publishes = assetData.get('publishes', {})

    lines = []
    lines.append(f"📋 {code} — {assetType} · {stage}")
    lines.append("")

    deptOrder = ['model', 'texture', 'shading', 'rig', 'groom']

    displayedDepts = [deptDisplayNames[d] for d in deptOrder if d in publishes]
    maxDeptLen = max(len(d) for d in displayedDepts) if displayedDepts else 8

    for dept in deptOrder:
        if dept not in publishes:
            continue

        pubInfo = publishes[dept]
        version = pubInfo.get('version', 0)
        status = pubInfo.get('status', 'unknown')

        emoji = statusEmojiMap.get(status, '❓')

        displayName = deptDisplayNames[dept]
        deptPadded = displayName.ljust(maxDeptLen)
        versionStr = f"v{version}"
        statusPadded = status.ljust(4)

        lines.append(f"{deptPadded}  {versionStr:>4}  {statusPadded} {emoji}")

    lines.append("")

    if useMarkdown and sgUrl:
        lines.append(f"<{sgUrl}|🔗 ShotGrid>")
    elif sgUrl:
        lines.append(f"🔗 ShotGrid: {sgUrl}")
    else:
        lines.append("🔗 ShotGrid")

    return "\n".join(lines)
