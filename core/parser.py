"""
Message parser for Google Spaces bot.

Extracts @mentions, shot/asset codes, and notes from raw Space messages.
"""

import re


def parseMessage(text):
    """Extract tagged user, shot/asset code, and note from Space message.
    
    Supports formats:
    1. "@user /note CODE note text"
    2. "hello @user shot CODE note text"
    3. "User, TIME\nCODE note text @user"
    4. "@user /note assetName note" (asset codes like chrNolmen)
    5. "/note show=SHOWCODE" (configuration command)
    
    Args:
        text: Raw message text from Google Space
        
    Returns:
        tuple: (taggedName, code, note, isConfigCommand, configShowCode)
            - taggedName: Name of @mentioned user or None
            - code: Shot/asset code or None
            - note: Remaining message text or empty string
            - isConfigCommand: True if this is a /note show=CODE command
            - configShowCode: Show code from config command or None
    """
    taggedName = None
    code = None
    note = ""
    isConfigCommand = False
    configShowCode = None
    
    configMatch = re.search(r'/note\s+show=(\w+)', text, re.IGNORECASE)
    if configMatch:
        isConfigCommand = True
        configShowCode = configMatch.group(1).strip()
        return taggedName, code, note, isConfigCommand, configShowCode
    
    atMatch = re.search(r'@([\w\-À-ÿ]+)', text, re.IGNORECASE)
    if atMatch:
        taggedName = atMatch.group(1).strip()
    
    commandMatch = re.search(r'/note\s+([\w._-]+)[,\s]*(.+)?', text, re.IGNORECASE)
    if commandMatch:
        code = commandMatch.group(1).strip().rstrip(',')
        note = commandMatch.group(2).strip() if commandMatch.group(2) else ""
    else:
        shotMatch = re.search(r'\b(\d{3}[a-z]{3}_\d{4})\b', text, re.IGNORECASE)
        if shotMatch:
            code = shotMatch.group(1)
            noteStart = shotMatch.end()
            remainingText = text[noteStart:].strip()
            
            atMentionPos = remainingText.find('@')
            if atMentionPos != -1:
                note = remainingText[:atMentionPos].strip()
            else:
                note = remainingText
        else:
            assetMatch = re.search(r'\b([a-z]{3}[A-Z][a-zA-Z]+)\b', text)
            if assetMatch:
                code = assetMatch.group(1)
                noteStart = assetMatch.end()
                remainingText = text[noteStart:].strip()
                
                atMentionPos = remainingText.find('@')
                if atMentionPos != -1:
                    note = remainingText[:atMentionPos].strip()
                else:
                    note = remainingText
    
    return taggedName, code, note, isConfigCommand, configShowCode


def extractShotCode(text):
    """Extract shot code pattern from text.
    
    Looks for pattern: 3 digits + 3 letters + underscore + 4 digits
    Example: 306dtt_1440
    
    Args:
        text: Text to search
        
    Returns:
        str: Shot code or None if not found
    """
    match = re.search(r'\b(\d{3}[a-z]{3}_\d{4})\b', text, re.IGNORECASE)
    return match.group(1) if match else None
