"""
Reply formatter for rdo_googlebot.

Formats bot replies for Google Spaces with ShotGrid links and status info.
"""


def formatReply(taggedName, code, note, sgData, senderName=None):
    """Format bot reply for Google Space (single line, plain text).
    
    Format: ✅ recorded: from SENDER to RECIPIENT - Please check CODE, NOTE → ShotGrid
    
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
    
    parts = ["✅ recorded:"]
    
    if senderName:
        parts.append(f"from {senderName}")
    
    if taggedName:
        parts.append(f"to {taggedName}")
    
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
    
    Format: ✅ recorded: from SENDER to RECIPIENT - Please check CODE, NOTE → ShotGrid
    
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
    
    parts = ["✅ recorded:"]
    
    if senderName:
        parts.append(f"from {senderName}")
    
    if taggedName:
        parts.append(f"to {taggedName}")
    
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
