#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Pipeline bot reply script - Multi-code support.
Usage: python bot_reply.py "<raw message from Space>"
Example: python bot_reply.py "@lpare /note 306dtt_1000 check qc, chrNolmen rig broken"

Only responds to messages with /note command + @mention.
Shows unknown codes in reply instead of staying silent.
"""

import requests
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.parser import parseAllCodes

WEBHOOK = "https://chat.googleapis.com/v1/spaces/AAQA_zvdsdQ/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=Kk172XQnlzDx9YIbQsbj7CcsS8wQJhH5901P99Una4E"
LOOKUP_URL = "http://mtl-webapps01/sg_dependencies/api/sg/lookup"


def lookup(code):
    r = requests.get(LOOKUP_URL, params={"q": code}, timeout=10)
    return r.json()


def get_sg_link(data):
    """Extract ShotGrid link from lookup response."""
    links = data.get("links", {})
    return links.get("shot") or links.get("version") or links.get("asset", "")


def formatMultiCodeReply(taggedNames, codeSegments, tractorUrl):
    """Format reply for multiple codes with per-code notes.
    
    Args:
        taggedNames: List of @mentioned users
        codeSegments: List of dicts with 'code', 'note', 'found', 'sgLink', 'type'
        tractorUrl: Tractor log URL or None
        
    Returns:
        str: Formatted reply (single or multi-line)
    """
    validSegments = [s for s in codeSegments if s.get('found')]
    unknownSegments = [s for s in codeSegments if not s.get('found')]
    
    totalItems = len(validSegments) + len(unknownSegments)
    if tractorUrl:
        totalItems += 1
    
    if totalItems == 0:
        return None
    
    if totalItems == 1 and not tractorUrl and len(unknownSegments) == 0:
        segment = validSegments[0]
        code = segment['code']
        note = segment.get('note', '')
        sgLink = segment.get('sgLink')
        
        taggedStr = ' '.join(taggedNames) if taggedNames else ''
        
        parts = [u"\u2705 recorded:"]
        if taggedStr:
            parts.append("to {}".format(taggedStr))
        parts.append("-")
        parts.append("Please check {}".format(code))
        if note:
            parts.append(", {}".format(note))
        
        if sgLink:
            parts.append("<{}|\u2192 ShotGrid>".format(sgLink))
        else:
            parts.append(u"\u2192 ShotGrid")
        
        return " ".join(parts)
    
    lines = []
    itemWord = 'items' if totalItems > 1 else 'item'
    lines.append(u"\u2705 Recorded \u2014 {} {}".format(totalItems, itemWord))
    
    if taggedNames:
        mentionStr = ' '.join(["@{}".format(name) for name in taggedNames])
        lines.append("{} \u2014 please check:".format(mentionStr))
    else:
        lines.append("Please check:")
    
    for segment in validSegments:
        code = segment['code']
        note = segment.get('note', '')
        sgLink = segment.get('sgLink')
        
        if sgLink:
            linkPart = "<{}|\u2192 ShotGrid>".format(sgLink)
        else:
            linkPart = u"\u2192 ShotGrid"
        
        if note:
            lines.append("- {} {} ({})".format(code, linkPart, note))
        else:
            lines.append("- {} {}".format(code, linkPart))
    
    for segment in unknownSegments:
        code = segment['code']
        note = segment.get('note', '')
        
        if note:
            lines.append("- {} Unknown shot/asset ({})".format(code, note))
        else:
            lines.append("- {} Unknown shot/asset".format(code))
    
    if tractorUrl:
        lines.append("- <{}|Tractor log: {}>".format(tractorUrl, tractorUrl))
    
    return "\n".join(lines)


def send(text):
    r = requests.post(WEBHOOK, json={"text": text}, timeout=10)
    print(r.status_code)


if __name__ == "__main__":
    raw = " ".join(sys.argv[1:])
    
    parsed = parseAllCodes(raw)
    
    if not parsed['hasNoteCommand']:
        sys.exit(0)
    
    if not parsed['taggedNames']:
        sys.exit(0)
    
    if not parsed['codeSegments']:
        sys.exit(0)
    
    codeSegments = []
    for segment in parsed['codeSegments']:
        code = segment['code']
        note = segment.get('note', '')
        
        data = lookup(code)
        
        codeSegments.append({
            'code': code,
            'note': note,
            'found': data.get('found', False),
            'sgLink': get_sg_link(data) if data.get('found') else None,
            'type': data.get('type')
        })
    
    reply = formatMultiCodeReply(
        taggedNames=parsed['taggedNames'],
        codeSegments=codeSegments,
        tractorUrl=parsed['tractorUrl']
    )
    
    if reply:
        send(reply)