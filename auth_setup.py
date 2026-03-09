#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
One-time OAuth setup for Google Tasks API.

Downloads credentials.json from Google Cloud Console first, then run:
    rez env python-3.11.9 -- python auth_setup.py

This opens a browser for authorization and saves token.json for future use.
"""

import os
import sys
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Scopes required for Google Tasks API
SCOPES = ['https://www.googleapis.com/auth/tasks']

CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'


def main():
    """Run OAuth 2.0 authorization flow and save token."""
    projectRoot = os.path.dirname(os.path.abspath(__file__))
    credentialsPath = os.path.join(projectRoot, CREDENTIALS_FILE)
    tokenPath = os.path.join(projectRoot, TOKEN_FILE)

    if not os.path.exists(credentialsPath):
        print(f"❌ Error: {CREDENTIALS_FILE} not found")
        print()
        print("Setup steps:")
        print("1. Go to https://console.cloud.google.com/apis/credentials")
        print("2. Select project: pipeline-bot-488915")
        print("3. Create OAuth 2.0 Client ID (Desktop app)")
        print("4. Download credentials as 'credentials.json'")
        print(f"5. Place in: {projectRoot}")
        print()
        sys.exit(1)

    print("=" * 60)
    print("Google Tasks API - OAuth Setup")
    print("=" * 60)
    print()

    creds = None

    # Check if token already exists
    if os.path.exists(tokenPath):
        print(f"⚠️  {TOKEN_FILE} already exists")
        response = input("Overwrite and re-authorize? (y/N): ").strip().lower()
        if response != 'y':
            print("Cancelled.")
            sys.exit(0)
        os.remove(tokenPath)
        print()

    # Run OAuth flow
    print("Starting OAuth 2.0 authorization flow...")
    print("A browser window will open for authorization.")
    print()

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            credentialsPath, SCOPES
        )
        creds = flow.run_local_server(port=0)

        # Save credentials for future use
        with open(tokenPath, 'w') as token:
            token.write(creds.to_json())

        print()
        print("=" * 60)
        print(f"✅ Authorization successful!")
        print(f"Token saved to: {tokenPath}")
        print("=" * 60)
        print()
        print("You can now use Google Tasks API in the bot.")
        print("Make sure token.json is in .gitignore!")

    except Exception as exc:
        print()
        print(f"❌ Authorization failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
