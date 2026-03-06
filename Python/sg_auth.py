#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ShotGrid authentication module with 5-tier fallback system.

This module provides functions to establish a connection to ShotGrid
using multiple authentication methods in order of preference.
"""

import os
import sys
import ssl

import shotgun_api3


def _getApiKeyFileInfo():
    """Locate api.key file and parse credentials.

    Returns:
        tuple: (path, url, scriptName, apiKey) or (None, None, None, None)
    """
    projectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    possibleLocations = [
        os.path.join(os.path.dirname(__file__), "api.key"),
        os.path.join(projectRoot, "api.key"),
        os.path.join(os.getcwd(), "api.key"),
        os.path.expanduser("~/.shotgrid/api.key"),
    ]

    for apiKeyFile in possibleLocations:
        if not os.path.exists(apiKeyFile):
            continue

        url = None
        scriptName = None
        apiKey = None

        with open(apiKeyFile, 'r') as fileHandle:
            for line in fileHandle:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")

                    if key == 'SG_URL':
                        url = value
                    elif key == 'SG_SCRIPT_NAME':
                        scriptName = value
                    elif key == 'SG_SCRIPT_KEY':
                        apiKey = value

        if apiKey:
            return apiKeyFile, url, scriptName, apiKey

    return None, None, None, None


def readApiKeyFile():
    """
    Read SG_URL, SG_SCRIPT_NAME and SG_SCRIPT_KEY from api.key file.

    The api.key file should contain:
        SG_URL=https://your-site.shotgrid.autodesk.com
        SG_SCRIPT_NAME=your_script_name
        SG_SCRIPT_KEY=your_api_key

    Returns:
        tuple: (url, scriptName, apiKey) or (None, None, None) if not found
    """
    _, url, scriptName, apiKey = _getApiKeyFileInfo()
    return url, scriptName, apiKey


def getShotgridAuthInfo():
    """Return ShotGrid auth details without exposing secrets.

    Returns:
        dict: Auth source and config metadata for diagnostics.
    """
    envUrl = os.environ.get('SHOTGRID_URL')
    envScript = os.environ.get('SHOTGRID_SCRIPT_NAME')
    envKey = os.environ.get('SHOTGRID_API_KEY')

    authMethod = None
    url = None
    scriptName = None
    apiKeyFile = None

    if envScript and envKey:
        authMethod = "environment variables"
        url = envUrl or "https://rodeofx.shotgrid.autodesk.com"
        scriptName = envScript
    else:
        apiKeyFile, fileUrl, fileScriptName, fileApiKey = _getApiKeyFileInfo()
        if fileApiKey:
            authMethod = "api.key file"
            url = fileUrl or "https://rodeofx.shotgrid.autodesk.com"
            scriptName = fileScriptName or ""

    return {
        "authMethod": authMethod or "none",
        "url": url,
        "scriptName": scriptName,
        "apiKeyFile": apiKeyFile,
        "envUrlPresent": bool(envUrl),
        "envScriptPresent": bool(envScript),
        "envKeyPresent": bool(envKey),
    }


def _create_sg_connection_with_retry(url, script_name, api_key):
    """Creates a ShotGrid connection with a retry for SSL errors."""
    try:
        return shotgun_api3.Shotgun(url, script_name=script_name, api_key=api_key)
    except ssl.SSLError as e:
        if "WRONG_VERSION_NUMBER" in str(e) and url.startswith("http://"):
            print(f"SSL WRONG_VERSION_NUMBER error for {url}, retrying with https...")
            https_url = url.replace("http://", "https://")
            return shotgun_api3.Shotgun(https_url, script_name=script_name, api_key=api_key)
        else:
            raise

def getShotgridConnection(args=None):
    """
    Get an authenticated ShotGrid connection using 5-tier fallback system.

    Tier 1: Environment variables (SHOTGRID_URL, SHOTGRID_SCRIPT_NAME, SHOTGRID_API_KEY)
    Tier 2: api.key file
    Tier 3: rdo_shotgun_core (Rodeo FX specific)
    Tier 4: Command line args (if provided)
    Tier 5: Default Rodeo FX URL with error

    Args:
        args: Optional argparse namespace with sg_server, sg_script, sg_key

    Returns:
        Authenticated shotgun_api3.Shotgun instance

    Raises:
        ValueError: If required credentials are missing
    """
    url = None
    scriptName = None
    apiKey = None
    authMethod = None

    # Tier 1: Environment variables
    envUrl = os.environ.get('SHOTGRID_URL')
    envScript = os.environ.get('SHOTGRID_SCRIPT_NAME')
    envKey = os.environ.get('SHOTGRID_API_KEY')

    if envScript and envKey:
        url = envUrl or "https://rodeofx.shotgrid.autodesk.com"
        scriptName = envScript
        apiKey = envKey
        authMethod = "environment variables"
        print(f"✓ Using ShotGrid credentials from {authMethod}")
        return _create_sg_connection_with_retry(url, scriptName, apiKey)

    # Tier 2: api.key file
    fileUrl, fileScriptName, fileApiKey = readApiKeyFile()
    if fileApiKey:
        url = fileUrl or "https://rodeofx.shotgrid.autodesk.com"
        scriptName = fileScriptName or ""
        apiKey = fileApiKey
        authMethod = "api.key file"
        print(f"✓ Using ShotGrid credentials from {authMethod}")
        return _create_sg_connection_with_retry(url, scriptName, apiKey)

    # Tier 3: rdo_shotgun_core (Rodeo FX specific) - SKIPPED
    # This requires scriptName and applicationKey which we don't have
    # If you need this, provide credentials via api.key or environment variables

    # Tier 4: Command line args override
    if args:
        if hasattr(args, 'sg_server') and args.sg_server:
            url = args.sg_server
        if hasattr(args, 'sg_script') and args.sg_script:
            scriptName = args.sg_script
        if hasattr(args, 'sg_key') and args.sg_key:
            apiKey = args.sg_key

        if scriptName and apiKey:
            url = url or "https://rodeofx.shotgrid.autodesk.com"
            authMethod = "command line arguments"
            print(f"✓ Using ShotGrid credentials from {authMethod}")
            return _create_sg_connection_with_retry(url, scriptName, apiKey)

    # Tier 5: Failed - provide helpful error
    print("✗ ShotGrid connection failed: No valid credentials found")
    print("\nTried in order:")
    print("  1. Environment variables (SHOTGRID_SCRIPT_NAME, SHOTGRID_API_KEY)")
    print("  2. api.key file")
    print("  3. rdo_shotgun_core module")
    print("  4. Command line arguments")
    print("\nSince you're in a Rez environment with rdo_shotgun_core, this should work automatically.")
    print("If it doesn't, create an api.key file or set environment variables.")

    raise ValueError(
        "ShotGrid authentication failed. No valid credentials found via any method."
    )