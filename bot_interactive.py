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

from bots.sgbot import processSgCommand
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
            
            result = processSgCommand(rawMessage, useMarkdown=True, showCode=currentShowCode, spaceId=spaceId)
            
            if result.get('isConfigCommand'):
                print(result['reply'])
                print("-" * 60)
                
                try:
                    response = postToSpace(result['reply'])
                    print(f"✓ Posted to Space (HTTP {response.status_code})")
                except Exception as exc:
                    print(f"✗ Failed to post: {exc}")
                
                continue
            
            print(f"Parsed: @{result['taggedName'] or '(none)'} | {result['code'] or '(none)'} | {result['note'][:30] if result.get('note') else '(none)'}...")
            
            if result.get('sgData'):
                sgData = result['sgData']
                print(f"ShotGrid: {sgData.get('type')} | {sgData.get('status')} | Found: {sgData.get('found')}")
            
            print("\nReply:")
            print(result['reply'])
            print("-" * 60)
            
            try:
                response = postToSpace(result['reply'])
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
