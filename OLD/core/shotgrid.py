# -*- coding: utf-8 -*-
"""ShotGrid REST API client.

Handles authentication and queries for shots, assets, and versions.
READ-ONLY operations only.

Uses existing rdo_shotgun_core infrastructure when available via rez,
or falls back to api.key file authentication.
"""

import os
import sys


# ShotGrid base URL
SG_BASE_URL = "https://rodeofx.shotgrid.autodesk.com"


def getShotgridConnection():
    """Get authenticated ShotGrid connection using existing infrastructure.

    Returns:
        Authenticated shotgun_api3.Shotgun instance

    Raises:
        ImportError: If shotgun_api3 not available
        ValueError: If authentication fails
    """
    # Try importing sg_auth from references (existing auth infrastructure)
    scriptDir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    referencesDir = os.path.join(scriptDir, 'references')

    if os.path.exists(referencesDir) and referencesDir not in sys.path:
        sys.path.insert(0, referencesDir)

    try:
        from sg_auth import getShotgridConnection as getConnection
        return getConnection()
    except ImportError:
        # Fallback: use shotgun_api3 directly with api.key
        return getShotgridConnectionFallback()


def getShotgridConnectionFallback():
    """Fallback: authenticate with api.key file directly.

    Returns:
        Authenticated shotgun_api3.Shotgun instance

    Raises:
        ImportError: If shotgun_api3 not available
        FileNotFoundError: If api.key not found
        ValueError: If credentials are missing
    """
    try:
        import shotgun_api3
    except ImportError:
        raise ImportError(
            "shotgun_api3 not found. Run with rez:\n"
            "rez env python-3.11.9 shotgun_api3-3.3.4-rdo-1.0.0 rdo_shotgun_core-1.10.1 requests -- python bot_simulate.py"
        )

    # Find api.key
    scriptDir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    keyFile = os.path.join(scriptDir, 'api.key')

    if not os.path.exists(keyFile):
        raise FileNotFoundError(f"api.key not found at {keyFile}")

    # Parse api.key
    config = {}
    with open(keyFile, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip().strip('"').strip("'")

    sgUrl = config.get('SG_URL', SG_BASE_URL)
    sgScriptName = config.get('SG_SCRIPT_NAME')
    sgScriptKey = config.get('SG_SCRIPT_KEY')

    if not sgScriptKey:
        raise ValueError("SG_SCRIPT_KEY not found in api.key")
    if not sgScriptName:
        raise ValueError("SG_SCRIPT_NAME not found in api.key")

    return shotgun_api3.Shotgun(sgUrl, script_name=sgScriptName, api_key=sgScriptKey)


def buildShotgridUrl(entityType, entityId):
    """Build a ShotGrid web URL for an entity.

    Args:
        entityType: Entity type (e.g., "Shot", "Asset", "Version")
        entityId: Entity ID (int)

    Returns:
        Full ShotGrid URL string

    Examples:
        >>> buildShotgridUrl("Shot", 12345)
        'https://rodeofx.shotgrid.autodesk.com/detail/Shot/12345'
    """
    if not entityType or not entityId:
        return None
    return f"{SG_BASE_URL}/detail/{entityType}/{entityId}"


def lookupShot(shotCode, projectCode='lbp3', sg=None):
    """Lookup a shot by code in ShotGrid.

    Args:
        shotCode: Shot code (e.g., "306dtt_1440")
        projectCode: Project code (default: "lbp3")
        sg: Optional existing ShotGrid connection

    Returns:
        dict with keys:
            - found: True if shot found
            - type: "Shot"
            - id: Shot ID
            - code: Shot code
            - status: Status string
            - link: ShotGrid web URL
            - data: Full shot entity data

    Examples:
        >>> lookupShot("306dtt_1440")
        {
            'found': True,
            'type': 'Shot',
            'id': 12345,
            'code': '306dtt_1440',
            'status': 'In Progress',
            'link': 'https://rodeofx.shotgrid.autodesk.com/detail/Shot/12345',
            'data': {...}
        }
    """
    result = {
        'found': False,
        'type': 'Shot',
        'id': None,
        'code': None,
        'status': None,
        'link': None,
        'data': None
    }

    try:
        if sg is None:
            sg = getShotgridConnection()

        filters = [
            ['code', 'contains', shotCode],
            ['project.Project.name', 'is', projectCode]
        ]
        fields = ['id', 'code', 'sg_status_list', 'description', 'sg_sequence']

        shot = sg.find_one('Shot', filters, fields)

        if shot:
            result['found'] = True
            result['id'] = shot.get('id')
            result['code'] = shot.get('code')
            result['status'] = shot.get('sg_status_list')
            result['link'] = buildShotgridUrl('Shot', shot.get('id'))
            result['data'] = shot

    except Exception as e:
        print(f"Error looking up shot '{shotCode}': {e}")

    return result


def lookupAsset(assetCode, projectCode='lbp3', sg=None):
    """Lookup an asset by code in ShotGrid.

    Args:
        assetCode: Asset code (e.g., "char_mp")
        projectCode: Project code (default: "lbp3")
        sg: Optional existing ShotGrid connection

    Returns:
        dict with keys:
            - found: True if asset found
            - type: "Asset"
            - id: Asset ID
            - code: Asset code
            - status: Status string
            - link: ShotGrid web URL
            - data: Full asset entity data
    """
    result = {
        'found': False,
        'type': 'Asset',
        'id': None,
        'code': None,
        'status': None,
        'link': None,
        'data': None
    }

    try:
        if sg is None:
            sg = getShotgridConnection()

        filters = [
            ['code', 'contains', assetCode],
            ['project.Project.name', 'is', projectCode]
        ]
        fields = ['id', 'code', 'sg_status_list', 'description', 'sg_asset_type']

        asset = sg.find_one('Asset', filters, fields)

        if asset:
            result['found'] = True
            result['id'] = asset.get('id')
            result['code'] = asset.get('code')
            result['status'] = asset.get('sg_status_list')
            result['link'] = buildShotgridUrl('Asset', asset.get('id'))
            result['data'] = asset

    except Exception as e:
        print(f"Error looking up asset '{assetCode}': {e}")

    return result


def lookupEntity(query, projectCode='lbp3'):
    """Lookup a shot, asset, or version by code or ID.

    Tries in order:
    1. Shot (code contains query)
    2. Asset (code contains query)
    3. Version (id matches query if numeric)

    Args:
        query: Shot/asset code or version ID (string or int)
        projectCode: Project code (default: "lbp3")

    Returns:
        dict with keys:
            - found: True if entity found
            - type: "Shot", "Asset", "Version", or None
            - id: Entity ID
            - code: Entity code
            - status: Status string
            - link: ShotGrid web URL
            - data: Full entity data

    Examples:
        >>> lookupEntity("306dtt_1440")
        {
            'found': True,
            'type': 'Shot',
            'id': 12345,
            'code': '306dtt_1440',
            'status': 'In Progress',
            'link': 'https://rodeofx.shotgrid.autodesk.com/detail/Shot/12345',
            'data': {...}
        }
    """
    result = {
        'found': False,
        'type': None,
        'id': None,
        'code': None,
        'status': None,
        'link': None,
        'data': None
    }

    try:
        sg = getShotgridConnection()
    except Exception as e:
        print(f"Error connecting to ShotGrid: {e}")
        return result

    # Try Shot
    shotResult = lookupShot(query, projectCode, sg)
    if shotResult['found']:
        return shotResult

    # Try Asset
    assetResult = lookupAsset(query, projectCode, sg)
    if assetResult['found']:
        return assetResult

    # Try Version (if query is numeric)
    if str(query).isdigit():
        try:
            filters = [['id', 'is', int(query)]]
            fields = ['id', 'code', 'sg_status_list', 'description']

            version = sg.find_one('Version', filters, fields)

            if version:
                result['found'] = True
                result['type'] = 'Version'
                result['id'] = version.get('id')
                result['code'] = version.get('code')
                result['status'] = version.get('sg_status_list')
                result['link'] = buildShotgridUrl('Version', version.get('id'))
                result['data'] = version
                return result

        except Exception as e:
            print(f"Error looking up version '{query}': {e}")

    return result
