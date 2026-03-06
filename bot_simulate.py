#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CLI demo tool for rdo_googlebot.

Simulates the Google Spaces bot experience. Paste a real Space message,
the tool parses it, queries ShotGrid, and prints a formatted bot reply.

Usage:
    python bot_simulate.py "Eileen Bocanegra, 10:41 AM\n306dtt_1440 not seeing MP @Louis Pare"
    
    # With rez
    rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 -- python bot_simulate.py

Examples:
    # Direct code with /sg command
    python bot_simulate.py "@Louis Paré /sg 306dtt_1440 not seeing the MP in the bg"
    
    # Natural Space message format
    python bot_simulate.py "Eileen Bocanegra, 10:41 AM
    306dtt_1440 still not seeing the MP in the bg. @Louis Pare"
    
    # Interactive mode (no args)
    python bot_simulate.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bots.sgbot import processSgCommandVerbose


def main():
    """Main CLI entry point."""
    if len(sys.argv) > 1:
        rawMessage = " ".join(sys.argv[1:])
    else:
        print("=" * 60)
        print("rdo_googlebot — CLI Demo")
        print("=" * 60)
        print("\nPaste a Google Space message (Ctrl+D when done):")
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
    
    result = processSgCommandVerbose(rawMessage, useMarkdown=False, showCode="lbp3")
    
    sys.exit(0 if result['success'] else 1)


if __name__ == "__main__":
    main()
