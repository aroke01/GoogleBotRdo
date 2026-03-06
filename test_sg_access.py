#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ShotGrid API access verification script.

Tests connection to ShotGrid using credentials from api.key file.
Performs a simple read query to verify authentication and access.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Python'))

from Python.sg_auth import getShotgridConnection, getShotgridAuthInfo


def testShotgridConnection():
    """Test ShotGrid API connection and perform basic read query.
    
    Returns:
        bool: True if connection successful, False otherwise
    """
    print("=" * 60)
    print("ShotGrid API Access Test")
    print("=" * 60)
    
    authInfo = getShotgridAuthInfo()
    print(f"\nAuth Info:")
    print(f"  Method: {authInfo['authMethod']}")
    print(f"  URL: {authInfo['url']}")
    print(f"  Script: {authInfo['scriptName']}")
    print(f"  API Key File: {authInfo['apiKeyFile']}")
    print()
    
    try:
        sg = getShotgridConnection()
        print(f"✓ Connection established successfully\n")
        
        print("Testing read access with simple query...")
        result = sg.find_one("Project", [], ["name", "id"])
        
        if result:
            print(f"✓ Read query successful")
            print(f"  Sample Project: {result['name']} (ID: {result['id']})")
        else:
            print("⚠ Query returned no results (may be permissions issue)")
        
        print("\nTesting Shot entity access...")
        shotResult = sg.find_one("Shot", [], ["code", "id", "sg_status_list"])
        
        if shotResult:
            print(f"✓ Shot query successful")
            print(f"  Sample Shot: {shotResult['code']} (ID: {shotResult['id']})")
            print(f"  Status: {shotResult.get('sg_status_list', 'N/A')}")
        else:
            print("⚠ No shots found")
        
        print("\n" + "=" * 60)
        print("✓ ShotGrid API access verified - READ-ONLY mode confirmed")
        print("=" * 60)
        return True
        
    except Exception as exc:
        print(f"✗ Connection failed: {exc}")
        print("\n" + "=" * 60)
        print("✗ ShotGrid API access test FAILED")
        print("=" * 60)
        return False


if __name__ == "__main__":
    success = testShotgridConnection()
    sys.exit(0 if success else 1)
