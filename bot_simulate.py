#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CLI demo tool for rdo_googlebot.

Simulates the Google Spaces bot experience. Paste a real Space message,
the tool parses it, queries ShotGrid, and prints a formatted bot reply.

Supports multiple codes with per-code notes:
    @user /sg code1 note1, code2 note2

Usage:
    python bot_simulate.py "@lpare /sg 306dtt_1440 check qc, 306dtt_0200 cache broken"
    
    # With rez
    rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_simulate.py

Examples:
    # Multiple codes with per-code notes
    python bot_simulate.py "@lpare /sg 306dtt_1440 check qc, chrNolmen rig broken"
    
    # Multiple codes with shared note
    python bot_simulate.py "@lpare /sg 306dtt_1440 518dvd_4300 both have cache issues"
    
    # Single code
    python bot_simulate.py "@lpare /sg 306dtt_1440 cache is broken"
    
    # Interactive mode (no args)
    python bot_simulate.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.parser import parseAllCodes
from core.shotgrid import lookupEntity, getAssetInfo
from core.formatter import formatMultiCodeReply, formatAssetInfo
from core.webhook import postToSpace


def main():
    """Main CLI entry point."""
    if len(sys.argv) > 1:
        rawMessage = " ".join(sys.argv[1:])
    else:
        print("=" * 60)
        print("rdo_googlebot — Multi-Code Bot Simulator")
        print("=" * 60)
        print("\nPaste a Google Space message (Ctrl+D when done):")
        print("Format: @user /sg code1 note1, code2 note2")
        print()
        
        lines = []
        try:
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            pass
        
        rawMessage = "\n".join(lines)
        
        if not rawMessage.strip():
            print("\n❓ No message provided.")
            sys.exit(1)
    
    print("=" * 60)
    print("Processing message...")
    print("=" * 60)
    print()

    showCode = "lbp3"

    parsed = parseAllCodes(rawMessage)

    if not parsed['hasNoteCommand']:
        print("⚠️  No /sg command found, staying silent.")
        print("   (This prevents flooding - only /sg commands trigger bot)")
        sys.exit(0)

    if parsed['subcommand'] == 'info':
        assetCode = parsed['subcommandCode']
        if not assetCode:
            print("⚠️  No asset code provided for info subcommand.")
            sys.exit(0)

        print(f"Info subcommand detected for asset: {assetCode}")
        print()

        assetData = getAssetInfo(assetCode, showCode)

        reply = formatAssetInfo(assetData, useMarkdown=True)

        print("=" * 60)
        print("Bot reply (posting to Space):")
        print("=" * 60)
        print(reply)
        print("=" * 60)
        print()

        try:
            response = postToSpace(reply)
            print(f"✓ Posted to Space (HTTP {response.status_code})")
            sys.exit(0)
        except Exception as exc:
            print(f"✗ Failed to post: {exc}")
            sys.exit(1)

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
    
    showCode = "lbp3"
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
    
    if not validCodeSegments:
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
        sys.exit(0)
    except Exception as exc:
        print(f"✗ Failed to post: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
