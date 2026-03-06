#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test script for bot_simulate.py

Quick test to verify the bot components work correctly.
"""

from core.parser import parseMessage
from core.shotgrid import lookupEntity
from core.formatter import formatBotReply

# Test message
testMessage = """Eileen Bocanegra, 10:41 AM
306dtt_1440 still not seeing the MP in the bg. @Louis Pare"""

print("=" * 60)
print("Testing rdo_googlebot components")
print("=" * 60)
print()

# Test 1: Parser
print("1. Testing parser...")
parsed = parseMessage(testMessage)
print(f"   Sender:    {parsed.get('sender')}")
print(f"   Mention:   {parsed.get('mention')}")
print(f"   Shot Code: {parsed.get('shotCode')}")
print(f"   Note:      {parsed.get('note')}")
print()

# Test 2: ShotGrid lookup
print("2. Testing ShotGrid lookup...")
shotCode = parsed.get('shotCode')
if shotCode:
    print(f"   Looking up '{shotCode}' in ShotGrid...")
    try:
        sgResult = lookupEntity(shotCode, projectCode='lbp3')
        if sgResult['found']:
            print(f"   ✓ Found: {sgResult['type']} (ID: {sgResult['id']})")
            print(f"   ✓ Status: {sgResult['status']}")
            print(f"   ✓ Link: {sgResult['link']}")
        else:
            print(f"   ✗ Not found in ShotGrid")
    except Exception as e:
        print(f"   ✗ Error: {e}")
else:
    print("   ✗ No shot code found to look up")
    sgResult = None
print()

# Test 3: Formatter
print("3. Testing formatter...")
reply = formatBotReply(
    parsed.get('mention'),
    parsed.get('shotCode'),
    parsed.get('note'),
    sgResult
)
print("   Generated reply:")
print()
print(reply)
print()

print("=" * 60)
print("Test complete!")
print("=" * 60)
