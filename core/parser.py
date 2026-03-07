"""
Message parser for Google Spaces bot.

Extracts @mentions, shot/asset codes, and notes from raw Space messages.
"""

import re


def parseMessage(text):
    """Extract tagged user, shot/asset code, and note from Space message.
    
    Supports formats:
    1. "@user /sg CODE note text"
    2. "hello @user shot CODE note text"
    3. "User, TIME\nCODE note text @user"
    4. "@user /sg assetName note" (asset codes like chrNolmen)
    5. "/sg show=SHOWCODE" (configuration command)
    
    Args:
        text: Raw message text from Google Space
        
    Returns:
        tuple: (taggedName, code, note, isConfigCommand, configShowCode)
            - taggedName: Name of @mentioned user or None
            - code: Shot/asset code or None
            - note: Remaining message text or empty string
            - isConfigCommand: True if this is a /sg show=CODE command
            - configShowCode: Show code from config command or None
    """
    taggedName = None
    code = None
    note = ""
    isConfigCommand = False
    configShowCode = None
    
    configMatch = re.search(r'/sg\s+show=(\w+)', text, re.IGNORECASE)
    if configMatch:
        isConfigCommand = True
        configShowCode = configMatch.group(1).strip()
        return taggedName, code, note, isConfigCommand, configShowCode
    
    atMatch = re.search(r'@([\w\-À-ÿ]+)', text, re.IGNORECASE)
    if atMatch:
        taggedName = atMatch.group(1).strip()
    
    commandMatch = re.search(r'/sg\s+([\w._-]+)[,\s]*(.+)?', text, re.IGNORECASE)
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


def parseAllCodes(text):
    """Extract all codes with per-code notes, Tractor URL, and @mentions.
    
    Supports comma-separated format for per-code notes:
        "@user /sg code1 note1, code2 note2, code3 note3"
    
    Or space-separated format for shared note:
        "@user /sg code1 code2 shared note text"
    
    Args:
        text: Raw message text from Google Space
        
    Returns:
        dict: {
            'hasNoteCommand': bool,
            'taggedNames': [str, ...],
            'codeSegments': [
                {'code': str, 'note': str, 'type': 'shot'|'version'|'versionId'|'asset'},
                ...
            ],
            'tractorUrl': str or None,
            'sharedNote': str or None
        }
    """
    result = {
        'hasNoteCommand': False,
        'taggedNames': [],
        'codeSegments': [],
        'tractorUrl': None,
        'sharedNote': None
    }
    
    if not re.search(r'/sg\b', text, re.IGNORECASE):
        return result
    
    result['hasNoteCommand'] = True
    
    allMentions = re.findall(r'@([\w\-À-ÿ]+)', text, re.IGNORECASE)
    result['taggedNames'] = [m.strip() for m in allMentions]
    
    tractorMatch = re.search(r'(https?://[^\s]*tractor[^\s]*)', text, re.IGNORECASE)
    if tractorMatch:
        result['tractorUrl'] = tractorMatch.group(1)
    
    # Match /sg followed by content, handling both "/sg @user code" and "@user /sg code"
    noteCommandMatch = re.search(r'/sg\s+(.+)', text, re.IGNORECASE)
    if not noteCommandMatch:
        # Try alternate format: content before /sg
        beforeSgMatch = re.search(r'(.+?)\s+/sg', text, re.IGNORECASE)
        if beforeSgMatch:
            afterNote = beforeSgMatch.group(1).strip()
        else:
            return result
    else:
        afterNote = noteCommandMatch.group(1).strip()
    
    if result['tractorUrl']:
        afterNote = afterNote.replace(result['tractorUrl'], '').strip()
    
    for mention in result['taggedNames']:
        afterNote = re.sub(r'@' + re.escape(mention) + r'\b', '', afterNote, flags=re.IGNORECASE).strip()
    
    if ',' in afterNote:
        segments = [s.strip() for s in afterNote.split(',') if s.strip()]
        
        for segment in segments:
            codeInfo = extractCodeFromSegment(segment)
            if codeInfo:
                result['codeSegments'].append(codeInfo)
    else:
        allCodes = []
        
        shotCodes = re.findall(r'\b(\d{3}[a-z]{3}_\d{4})\b', afterNote, re.IGNORECASE)
        for code in shotCodes:
            allCodes.append({'code': code, 'type': 'shot', 'pos': afterNote.lower().find(code.lower())})
        
        versionCodes = re.findall(r'\b(\d{3}[a-z]{3}_\d{4}\.[a-zA-Z0-9._]+)\b', afterNote, re.IGNORECASE)
        for code in versionCodes:
            allCodes.append({'code': code, 'type': 'version', 'pos': afterNote.lower().find(code.lower())})
        
        versionIds = re.findall(r'(?:ID:\s*)?(\d{7})\b', afterNote)
        for vid in versionIds:
            allCodes.append({'code': vid, 'type': 'versionId', 'pos': afterNote.find(vid)})
        
        assetCodes = re.findall(r'\b([a-z]{3}[A-Z][a-zA-Z]+)\b', afterNote)
        for code in assetCodes:
            if not any(c['code'].lower() == code.lower() for c in allCodes):
                allCodes.append({'code': code, 'type': 'asset', 'pos': afterNote.find(code)})
        
        allCodes.sort(key=lambda x: x['pos'])
        
        if allCodes:
            noteText = afterNote
            for codeInfo in allCodes:
                noteText = noteText.replace(codeInfo['code'], '', 1)
            noteText = re.sub(r'\s+', ' ', noteText).strip()
            noteText = re.sub(r'^[,\s]+|[,\s]+$', '', noteText)
            
            if noteText:
                result['sharedNote'] = noteText
            
            for codeInfo in allCodes:
                result['codeSegments'].append({
                    'code': codeInfo['code'],
                    'note': '',
                    'type': codeInfo['type']
                })
    
    return result


def extractCodeFromSegment(segment):
    """Extract code and note from a comma-separated segment.
    
    Args:
        segment: Text segment like "306dtt_1440 check the qc please"
        
    Returns:
        dict: {'code': str, 'note': str, 'type': str} or None
    """
    shotMatch = re.search(r'\b(\d{3}[a-z]{3}_\d{4})\b', segment, re.IGNORECASE)
    if shotMatch:
        code = shotMatch.group(1)
        note = segment.replace(code, '', 1).strip()
        return {'code': code, 'note': note, 'type': 'shot'}
    
    versionMatch = re.search(r'\b(\d{3}[a-z]{3}_\d{4}\.[a-zA-Z0-9._]+)\b', segment, re.IGNORECASE)
    if versionMatch:
        code = versionMatch.group(1)
        note = segment.replace(code, '', 1).strip()
        return {'code': code, 'note': note, 'type': 'version'}
    
    versionIdMatch = re.search(r'(?:ID:\s*)?(\d{7})\b', segment)
    if versionIdMatch:
        code = versionIdMatch.group(1)
        note = segment.replace(versionIdMatch.group(0), '', 1).strip()
        return {'code': code, 'note': note, 'type': 'versionId'}
    
    assetMatch = re.search(r'\b([a-z]{3}[A-Z][a-zA-Z]+)\b', segment)
    if assetMatch:
        code = assetMatch.group(1)
        note = segment.replace(code, '', 1).strip()
        return {'code': code, 'note': note, 'type': 'asset'}
    
    return None
