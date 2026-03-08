#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Post bot reply to Google Space.

Parses a Space message, queries ShotGrid, and posts the formatted reply
directly to the Google Space via webhook.

Supports multi-code format:
    @user /sg code1 note1, code2 note2

Usage:
    python bot_post.py "@Louis Paré /sg 306dtt_1440 not seeing the MP"

    # With rez
    rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_post.py

Examples:
    # Single code
    python bot_post.py "@Louis Paré /sg 306dtt_1440 not seeing the MP in the bg"

    # Multiple codes with per-code notes
    python bot_post.py "@lpare /sg 306dtt_1440 check qc, chrNolmen rig broken"
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.parser import parseAllCodes
from core.shotgrid import lookupEntity
from core.formatter import formatMultiCodeReply
from core.webhook import postToSpace
from core.config import getSpaceIdFromApiKey, getShowFromSpaceId


def main():
    """Main entry point for posting to Space."""
    if len(sys.argv) < 2:
        print("Usage: python bot_post.py \"<message>\"")
        print("\nExamples:")
        print('  python bot_post.py "@Louis Paré /sg 306dtt_1440 not seeing the MP"')
        print('  python bot_post.py "@lpare /sg 306dtt_1440 check qc, chrNolmen rig broken"')
        sys.exit(1)

    spaceId = getSpaceIdFromApiKey()
    showCode = None

    if spaceId:
        showCode = getShowFromSpaceId(spaceId)

    if not showCode:
        showCode = "lbp3"

    rawMessage = " ".join(sys.argv[1:])

    print("=" * 60)
    print("Processing message and posting to Space...")
    print("=" * 60)
    print(f"\nSpace ID: {spaceId or '(not found)'}")
    print(f"Show: {showCode}")
    print(f"Input: {rawMessage[:100]}...")
    print()

    parsed = parseAllCodes(rawMessage)

    if not parsed['hasNoteCommand']:
        print("⚠️  No /sg command found, staying silent.")
        sys.exit(0)

    if not parsed['taggedNames']:
        print("⚠️  No @mention found, staying silent.")
        sys.exit(0)

    if not parsed['codeSegments']:
        print("⚠️  No codes found, staying silent.")
        sys.exit(0)

    print(f"Parsed:")
    print(f"  @mentions: {', '.join(parsed['taggedNames'])}")
    print(f"  Codes found: {len(parsed['codeSegments'])}")
    if parsed['tractorUrl']:
        print(f"  Tractor URL: {parsed['tractorUrl']}")
    if parsed['sharedNote']:
        print(f"  Shared note: {parsed['sharedNote']}")
    print()

    validCodeSegments = []
    invalidCount = 0

    print("Querying ShotGrid...")
    for segment in parsed['codeSegments']:
        code = segment['code']
        sgData = lookupEntity(code, showCode)

        if sgData.get('found'):
            validCodeSegments.append({
                'code': code,
                'note': segment.get('note', ''),
                'sgLink': sgData.get('link')
            })
            print(f"  ✓ {code} — {sgData.get('type')} (status: {sgData.get('status')})")
        else:
            invalidCount += 1
            print(f"  ✗ {code} — not found")

    print()

    if not validCodeSegments and invalidCount == 0:
        print("⚠️  No valid SG codes found, staying silent.")
        sys.exit(0)

    reply = formatMultiCodeReply(
        taggedNames=parsed['taggedNames'],
        validCodeSegments=validCodeSegments,
        tractorUrl=parsed['tractorUrl'],
        invalidCount=invalidCount,
        sharedNote=parsed['sharedNote'],
        useMarkdown=True
    )

    print("=" * 60)
    print("Bot reply (posting to Space):")
    print("=" * 60)
    print(reply)
    print("=" * 60)
    print()

    try:
        response = postToSpace(reply)
        print(f"✓ Posted to Space (HTTP {response.status_code})")
        if spaceId:
            print(f"  Space: {spaceId}")
            print(f"  URL: https://mail.google.com/mail/u/0/#chat/space/{spaceId}")
        sys.exit(0)
    except Exception as exc:
        print(f"✗ Failed to post to Space: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
