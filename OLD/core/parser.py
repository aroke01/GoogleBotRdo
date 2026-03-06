# -*- coding: utf-8 -*-
"""Message parsing for Google Spaces messages.

Extracts @mentions, shot/asset codes, and notes from raw Space messages.
"""

import re


def parseMessage(rawMessage):
    """Parse a Google Space message to extract key components.

    Args:
        rawMessage: Raw text from Google Space (string).
                   Example: "Eileen Bocanegra, 10:41 AM\n306dtt_1440 still not seeing the MP in the bg. @Louis Pare"

    Returns:
        dict with keys:
            - mention: Name of person mentioned (e.g., "Louis Pare"), or None
            - shotCode: Shot or asset code (e.g., "306dtt_1440"), or None
            - note: The note/message text, cleaned up
            - sender: Person who sent the message (e.g., "Eileen Bocanegra"), or None

    Examples:
        >>> parseMessage("Eileen Bocanegra, 10:41 AM\\n306dtt_1440 still not seeing the MP @Louis Pare")
        {
            'mention': 'Louis Pare',
            'shotCode': '306dtt_1440',
            'note': '306dtt_1440 still not seeing the MP',
            'sender': 'Eileen Bocanegra'
        }
    """
    result = {
        'mention': None,
        'shotCode': None,
        'note': None,
        'sender': None
    }

    if not rawMessage:
        return result

    # Split into lines
    lines = rawMessage.strip().split('\n')

    # Extract sender from first line (format: "Name, Time")
    # Example: "Eileen Bocanegra, 10:41 AM"
    senderMatch = re.match(r'^(.+?),\s*\d+:\d+\s*(?:AM|PM)', lines[0])
    if senderMatch:
        result['sender'] = senderMatch.group(1).strip()
        # Message starts on second line
        messageText = '\n'.join(lines[1:]) if len(lines) > 1 else ''
    else:
        # No timestamp format, treat entire message as message text
        messageText = rawMessage

    # Extract @mention
    # Matches: @Louis Pare, @Louis Paré, etc.
    mentionMatch = re.search(r'@([A-Z][a-z]+(?:\s+[A-Z][a-zé]+)*)', messageText)
    if mentionMatch:
        result['mention'] = mentionMatch.group(1).strip()

    # Extract shot/asset code
    # Pattern: alphanumeric with underscores, typically like "306dtt_1440" or "char_mp"
    # Must start with alphanumeric, contain underscore, and end with alphanumeric
    shotCodeMatch = re.search(r'\b([a-zA-Z0-9]+_[a-zA-Z0-9_]+)\b', messageText)
    if shotCodeMatch:
        result['shotCode'] = shotCodeMatch.group(1)

    # Extract note: remove @mention, clean up whitespace
    note = messageText
    if result['mention']:
        # Remove @mention from note
        note = re.sub(r'@' + re.escape(result['mention']), '', note)

    # Clean up note: strip whitespace, normalize spaces
    note = ' '.join(note.split())
    result['note'] = note if note else None

    return result


def extractShotCode(text):
    """Extract shot or asset code from text.

    Args:
        text: String that may contain a shot/asset code.

    Returns:
        Shot/asset code string, or None if not found.

    Examples:
        >>> extractShotCode("306dtt_1440 looks good")
        '306dtt_1440'
        >>> extractShotCode("char_mp needs update")
        'char_mp'
    """
    if not text:
        return None

    shotCodeMatch = re.search(r'\b([a-zA-Z0-9]+_[a-zA-Z0-9_]+)\b', text)
    return shotCodeMatch.group(1) if shotCodeMatch else None


def extractMention(text):
    """Extract @mention from text.

    Args:
        text: String that may contain an @mention.

    Returns:
        Mentioned person's name (without @), or None if not found.

    Examples:
        >>> extractMention("Please check this @Louis Pare")
        'Louis Pare'
        >>> extractMention("@Louis Paré can you look?")
        'Louis Paré'
    """
    if not text:
        return None

    mentionMatch = re.search(r'@([A-Z][a-z]+(?:\s+[A-Z][a-zé]+)*)', text)
    return mentionMatch.group(1).strip() if mentionMatch else None


def cleanNote(text, mention=None):
    """Clean up note text by removing @mentions and normalizing whitespace.

    Args:
        text: Raw note text.
        mention: Optional mention name to remove from text.

    Returns:
        Cleaned note string.

    Examples:
        >>> cleanNote("306dtt_1440 still not seeing the MP @Louis Pare", "Louis Pare")
        '306dtt_1440 still not seeing the MP'
    """
    if not text:
        return ''

    note = text
    if mention:
        note = re.sub(r'@' + re.escape(mention), '', note)

    # Normalize whitespace
    note = ' '.join(note.split())
    return note
