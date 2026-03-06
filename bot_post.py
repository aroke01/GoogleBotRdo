#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Post bot reply to Google Space.

Parses a Space message, queries ShotGrid, and posts the formatted reply
directly to the Google Space via webhook.

Usage:
    python bot_post.py "@Louis Paré /sg 306dtt_1440 not seeing the MP"
    
    # With rez
    rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_post.py

Examples:
    # Direct code with /sg command
    python bot_post.py "@Louis Paré /sg 306dtt_1440 not seeing the MP in the bg"
    
    # Natural Space message format
    python bot_post.py "Eileen Bocanegra, 10:41 AM
    306dtt_1440 still not seeing the MP in the bg. @Louis Pare"
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bots.sgbot import processSgCommand
from core.webhook import postToSpace
from core.config import getSpaceIdFromApiKey, getShowFromSpaceId


def main():
    """Main entry point for posting to Space."""
    if len(sys.argv) < 2:
        print("Usage: python bot_post.py \"<message>\"")
        print("\nExample:")
        print('  python bot_post.py "@Louis Paré /sg 306dtt_1440 not seeing the MP"')
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
    
    result = processSgCommand(rawMessage, useMarkdown=True, showCode=showCode, spaceId=spaceId)
    
    if result.get('isConfigCommand'):
        print(f"\n{result['reply']}")
        print("=" * 60)
    else:
        print(f"\nParsed:")
        print(f"  Tagged: {result.get('taggedName') or '(none)'}")
        print(f"  Code: {result.get('code') or '(none)'}")
        print(f"  Note: {result.get('note') or '(none)'}")
        
        if result.get('sgData'):
            print(f"\nShotGrid:")
            print(f"  Found: {result['sgData'].get('found')}")
            print(f"  Type: {result['sgData'].get('type')}")
            print(f"  Status: {result['sgData'].get('status')}")
        
        print("\n" + "=" * 60)
        print("Bot reply (posting to Space):")
        print("=" * 60)
        print(result['reply'])
        print("=" * 60)
    
    try:
        response = postToSpace(result['reply'])
        print(f"\n✓ Posted to Space (HTTP {response.status_code})")
        print(f"  Space: AAQA_zvdsdQ")
        print(f"  URL: https://mail.google.com/mail/u/0/#chat/space/AAQA_zvdsdQ")
    except Exception as exc:
        print(f"\n✗ Failed to post to Space: {exc}")
        sys.exit(1)
    
    sys.exit(0 if result['success'] else 1)


if __name__ == "__main__":
    main()
