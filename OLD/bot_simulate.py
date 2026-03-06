#!/usr/bin/env python
"""bot_simulate.py — CLI demo for rdo_googlebot.

Simulates the Google Spaces bot experience:
1. Paste a raw Space message
2. Bot parses it, queries ShotGrid
3. Prints formatted reply to terminal
4. Optionally posts to Space via webhook

Usage:
    # Interactive mode (paste message)
    python bot_simulate.py

    # Command-line argument
    python bot_simulate.py "Eileen Bocanegra, 10:41 AM\n306dtt_1440 not seeing MP @Louis Pare"

    # With rez
    rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 requests -- python bot_simulate.py
"""

import sys
from bots.sgbot import processBotMessage


def main():
    """Main CLI entry point."""
    print('=' * 60)
    print('rdo_googlebot — CLI Simulator')
    print('=' * 60)
    print()

    # Get message input
    if len(sys.argv) > 1:
        # Message provided as command-line argument
        rawMessage = sys.argv[1]
    else:
        # Interactive mode
        print('Paste the raw Space message below (press Enter twice when done):')
        print()
        lines = []
        emptyCount = 0
        while True:
            try:
                line = input()
                if not line:
                    emptyCount += 1
                    if emptyCount >= 2:
                        break
                else:
                    emptyCount = 0
                    lines.append(line)
            except EOFError:
                break

        rawMessage = '\n'.join(lines)

    if not rawMessage.strip():
        print('Error: No message provided.')
        sys.exit(1)

    print()
    print('-' * 60)
    print('Input Message:')
    print('-' * 60)
    print(rawMessage)
    print()

    # Process message
    print('-' * 60)
    print('Processing...')
    print('-' * 60)

    result = processBotMessage(rawMessage, showCode='lbp3')

    # Display parsed components
    if result['parsed']:
        parsed = result['parsed']
        print()
        print('Parsed Components:')
        print(f"  Sender:    {parsed.get('sender') or 'N/A'}")
        print(f"  Mention:   {parsed.get('mention') or 'N/A'}")
        print(f"  Shot Code: {parsed.get('shotCode') or 'N/A'}")
        print(f"  Note:      {parsed.get('note') or 'N/A'}")

    # Display ShotGrid lookup result
    if result['sgResult']:
        sg = result['sgResult']
        print()
        print('ShotGrid Lookup:')
        if sg.get('found'):
            print(f"  Found:  Yes")
            print(f"  Type:   {sg.get('type')}")
            print(f"  Code:   {sg.get('code')}")
            print(f"  Status: {sg.get('status')}")
            print(f"  Link:   {sg.get('link')}")
        else:
            print(f"  Found:  No")

    # Display bot reply
    print()
    print('=' * 60)
    print('Bot Reply:')
    print('=' * 60)
    print()
    print(result['reply'])
    print()

    # Ask if user wants to post to Space
    print('-' * 60)
    postToSpace = input('Post this reply to Google Space? (y/N): ').strip().lower()

    if postToSpace == 'y':
        try:
            from bot_reply import postToSpace as sendToSpace
            sendToSpace(result['reply'])
            print('✅ Posted to Space successfully')
        except ImportError:
            print('⚠️ bot_reply.py not found - cannot post to Space')
        except Exception as e:
            print(f'⚠️ Error posting to Space: {e}')

    print()
    print('Done.')


if __name__ == '__main__':
    main()
