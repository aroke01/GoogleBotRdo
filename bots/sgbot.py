"""
ShotGrid bot logic for rdo_googlebot.

Main bot processing logic, reusable for Cloud Run and CLI tools.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.parser import parseMessage
from core.shotgrid import lookupEntity
from core.formatter import formatReply, formatReplyMarkdown
from core.config import setShowForSpace


def processConfigCommand(spaceId, showCode):
    """Process a Space configuration command.
    
    Args:
        spaceId: Google Chat Space ID
        showCode: Show code to configure (e.g., "lbp3")
        
    Returns:
        dict: {
            'success': bool,
            'reply': str (confirmation message),
            'isConfigCommand': True
        }
    """
    success = setShowForSpace(spaceId, showCode)
    
    if success:
        reply = f"✅ Space configured for show: *{showCode}*\n\nAll future commands will use show: {showCode}"
    else:
        reply = f"✗ Failed to save configuration for show: {showCode}"
    
    return {
        'success': success,
        'reply': reply,
        'isConfigCommand': True
    }


def processSgCommand(rawMessage, useMarkdown=False, showCode="lbp3", spaceId=None, senderName=None):
    """Process a ShotGrid command from Google Space message.
    
    Main bot logic:
    1. Parse message to extract @mention, code, note
    2. Check if config command (/sg show=CODE)
    3. Query ShotGrid for entity
    4. Format reply
    
    Args:
        rawMessage: Raw message text from Google Space
        useMarkdown: Use Markdown formatting (default: False)
        showCode: Show code for ShotGrid queries (default: lbp3)
        spaceId: Google Chat Space ID (for config commands)
        senderName: Name of message sender (optional, for Cloud Run)
        
    Returns:
        dict: {
            'success': bool,
            'reply': str (formatted reply text),
            'taggedName': str or None,
            'code': str or None,
            'note': str,
            'sgData': dict (ShotGrid lookup result),
            'isConfigCommand': bool
        }
    """
    if '/note' not in rawMessage.lower():
        return {
            'success': False,
            'reply': None,
            'taggedName': None,
            'code': None,
            'note': '',
            'sgData': None,
            'isConfigCommand': False
        }
    
    taggedName, code, note, isConfigCommand, configShowCode = parseMessage(rawMessage)
    
    if isConfigCommand:
        if spaceId:
            return processConfigCommand(spaceId, configShowCode)
        else:
            return {
                'success': False,
                'reply': "✗ Cannot configure Space: Space ID not available",
                'isConfigCommand': True
            }
    
    if not taggedName:
        return {
            'success': False,
            'reply': None,
            'taggedName': None,
            'code': None,
            'note': '',
            'sgData': None,
            'isConfigCommand': False
        }
    
    if not code:
        return {
            'success': False,
            'reply': None,
            'taggedName': None,
            'code': None,
            'note': '',
            'sgData': None,
            'isConfigCommand': False
        }
    
    sgData = lookupEntity(code, showCode)
    
    if useMarkdown:
        reply = formatReplyMarkdown(taggedName, code, note, sgData, senderName)
    else:
        reply = formatReply(taggedName, code, note, sgData, senderName)
    
    return {
        'success': sgData.get('found', False),
        'reply': reply,
        'taggedName': taggedName,
        'code': code,
        'note': note,
        'sgData': sgData,
        'isConfigCommand': False
    }


def processSgCommandVerbose(rawMessage, useMarkdown=False, showCode="lbp3", spaceId=None, senderName=None):
    """Process ShotGrid command with verbose debug output.
    
    Same as processSgCommand but prints parsing and lookup details.
    Useful for CLI debugging.
    
    Args:
        rawMessage: Raw message text from Google Space
        useMarkdown: Use Markdown formatting (default: False)
        showCode: Show code for ShotGrid queries (default: lbp3)
        spaceId: Google Chat Space ID (for config commands)
        senderName: Name of message sender (optional, for Cloud Run)
        
    Returns:
        dict: Same as processSgCommand
    """
    print("=" * 60)
    print("Processing message...")
    print("=" * 60)
    
    if '/note' not in rawMessage.lower():
        print("\n⚠️  No /note command found, staying silent.")
        return {
            'success': False,
            'reply': None,
            'taggedName': None,
            'code': None,
            'note': '',
            'sgData': None,
            'isConfigCommand': False
        }
    
    taggedName, code, note, isConfigCommand, configShowCode = parseMessage(rawMessage)
    
    if isConfigCommand:
        print(f"\nConfig command detected: show={configShowCode}")
        if spaceId:
            result = processConfigCommand(spaceId, configShowCode)
            print(f"\n{result['reply']}")
            return result
        else:
            reply = "✗ Cannot configure Space: Space ID not available"
            print(f"\n{reply}")
            return {
                'success': False,
                'reply': reply,
                'isConfigCommand': True
            }
    
    print(f"\nParsed:")
    print(f"  Tagged: {taggedName or '(none)'}")
    print(f"  Code: {code or '(none)'}")
    print(f"  Note: {note or '(none)'}")
    
    if not taggedName:
        print("\n⚠️  No @mention found, staying silent.")
        return {
            'success': False,
            'reply': None,
            'taggedName': None,
            'code': None,
            'note': '',
            'sgData': None,
            'isConfigCommand': False
        }
    
    if not code:
        print("\n⚠️  No code found, staying silent.")
        return {
            'success': False,
            'reply': None,
            'taggedName': None,
            'code': None,
            'note': '',
            'sgData': None,
            'isConfigCommand': False
        }
    
    print(f"\nQuerying ShotGrid for: {code}")
    sgData = lookupEntity(code, showCode)
    
    print(f"\nShotGrid result:")
    print(f"  Found: {sgData.get('found')}")
    print(f"  Type: {sgData.get('type')}")
    print(f"  ID: {sgData.get('id')}")
    print(f"  Status: {sgData.get('status')}")
    
    if useMarkdown:
        reply = formatReplyMarkdown(taggedName, code, note, sgData, senderName)
    else:
        reply = formatReply(taggedName, code, note, sgData, senderName)
    
    print("\n" + "=" * 60)
    print("Bot reply:")
    print("=" * 60)
    print(reply)
    print("=" * 60)
    
    return {
        'success': sgData.get('found', False),
        'reply': reply,
        'taggedName': taggedName,
        'code': code,
        'note': note,
        'sgData': sgData,
        'isConfigCommand': False
    }
