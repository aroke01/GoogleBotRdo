#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Interactive bot for rdo_googlebot.

Runs in a loop: paste Space message, bot queries ShotGrid and posts reply.
Press Ctrl+C to exit.

Usage:
    rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_interactive.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.parser import parseAllCodes
from core.shotgrid import lookupEntity, getAssetInfo, getDependencies
from core.formatter import formatMultiCodeReply, formatAssetInfo, formatDependencies, formatHelp
from core.webhook import postToSpace
from core.config import getSpaceIdFromApiKey, getShowFromSpaceId


def main():
    """Interactive loop for processing Space messages."""
    spaceId = getSpaceIdFromApiKey()
    showCode = None
    
    if spaceId:
        showCode = getShowFromSpaceId(spaceId)
    
    print("=" * 60)
    print("rdo_googlebot — Interactive Mode")
    print("=" * 60)
    print(f"\nSpace ID: {spaceId or '(not found)'}")
    
    if showCode:
        print(f"Show: {showCode} (configured)")
    else:
        print("Show: (not configured)")
        print("\n⚠️  To configure this Space, type: /sg show=SHOWCODE")
        print("   Example: /sg show=lbp3\n")
    
    print("\nPaste a Space message and press Enter.")
    print("Bot will query ShotGrid and post reply automatically.")
    print("Press Ctrl+C to exit.\n")
    print("=" * 60)
    
    while True:
        try:
            print("\nPaste message (or Ctrl+C to exit):")
            rawMessage = input("> ").strip()
            
            if not rawMessage:
                print("⚠️  Empty message, skipping...")
                continue
            
            print("\n" + "-" * 60)
            
            currentShowCode = getShowFromSpaceId(spaceId) if spaceId else None
            if not currentShowCode:
                currentShowCode = "lbp3"
            
            parsed = parseAllCodes(rawMessage)

            if not parsed['hasNoteCommand']:
                print("⚠️  No /sg command found, staying silent.")
                print("-" * 60)
                continue

            if parsed['subcommand'] == 'help':
                print("Help subcommand detected")
                print()

                reply = formatHelp(useMarkdown=True)

                print("Reply:")
                print(reply)
                print("-" * 60)

                try:
                    response = postToSpace(reply)
                    print(f"✓ Posted to Space (HTTP {response.status_code})")
                except Exception as exc:
                    print(f"✗ Failed to post: {exc}")

                continue

            if parsed['subcommand'] == 'info':
                assetCode = parsed['subcommandCode']
                if not assetCode:
                    print("⚠️  No asset code provided for info subcommand.")
                    print("-" * 60)
                    continue

                print(f"Info subcommand detected for asset: {assetCode}")
                print()

                assetData = getAssetInfo(assetCode, currentShowCode)

                reply = formatAssetInfo(assetData, useMarkdown=True)

                print("Reply:")
                print(reply)
                print("-" * 60)

                try:
                    response = postToSpace(reply)
                    print(f"✓ Posted to Space (HTTP {response.status_code})")
                except Exception as exc:
                    print(f"✗ Failed to post: {exc}")

                continue

            if parsed['subcommand'] == 'deps':
                depsCode = parsed['subcommandCode']
                if not depsCode:
                    print("⚠️  No code provided for deps subcommand.")
                    print("-" * 60)
                    continue

                print(f"Deps subcommand detected for: {depsCode}")
                print()

                depsData = getDependencies(depsCode, currentShowCode)

                reply = formatDependencies(depsData, useMarkdown=True)

                print("Reply:")
                print(reply)
                print("-" * 60)

                try:
                    response = postToSpace(reply)
                    print(f"✓ Posted to Space (HTTP {response.status_code})")
                except Exception as exc:
                    print(f"✗ Failed to post: {exc}")

                continue

            if not parsed['taggedNames']:
                print("⚠️  No @mention found, staying silent.")
                print("-" * 60)
                continue

            if not parsed['codeSegments']:
                print("⚠️  No codes found, staying silent.")
                print("-" * 60)
                continue
            
            print(f"Parsed:")
            print(f"  @mentions: {', '.join(parsed['taggedNames'])}")
            print(f"  Codes found: {len(parsed['codeSegments'])}")
            if parsed['tractorUrl']:
                print(f"  Tractor URL: {parsed['tractorUrl']}")
            if parsed['sharedNote']:
                print(f"  Shared note: {parsed['sharedNote']}")
            
            validCodeSegments = []
            invalidCount = 0
            
            print("\nQuerying ShotGrid...")
            for segment in parsed['codeSegments']:
                code = segment['code']
                sgData = lookupEntity(code, currentShowCode)
                
                if sgData.get('found'):
                    validCodeSegments.append({
                        'code': code,
                        'note': segment.get('note', ''),
                        'sgLink': sgData.get('link')
                    })
                    print(f"  ✓ {code} — {sgData.get('type')} (status: {sgData.get('status')})")
                else:
                    invalidCount += 1
                    validCodeSegments.append({
                        'code': code,
                        'note': segment.get('note', ''),
                        'sgLink': None
                    })
                    print(f"  ✗ {code} — not found")
            
            reply = formatMultiCodeReply(
                taggedNames=parsed['taggedNames'],
                validCodeSegments=[s for s in validCodeSegments if s['sgLink']],
                tractorUrl=parsed['tractorUrl'],
                invalidCount=invalidCount,
                sharedNote=parsed['sharedNote'],
                useMarkdown=True
            )
            
            print("\nReply:")
            print(reply)
            print("-" * 60)
            
            try:
                response = postToSpace(reply)
                print(f"✓ Posted to Space (HTTP {response.status_code})")
            except Exception as exc:
                print(f"✗ Failed to post: {exc}")
            
        except KeyboardInterrupt:
            print("\n\n" + "=" * 60)
            print("Exiting interactive mode. Goodbye!")
            print("=" * 60)
            sys.exit(0)
        except Exception as exc:
            print(f"\n✗ Error: {exc}")
            print("Try again or press Ctrl+C to exit.")


if __name__ == "__main__":
    main()
