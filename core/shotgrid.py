"""
ShotGrid query module for rdo_googlebot.

Handles authentication and READ-ONLY queries for shots, assets, and versions.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Python'))

from Python.sg_auth import getShotgridConnection
from Python.asset_resolver import resolveLatestPerDept


def getSgToken():
    """Get authenticated ShotGrid connection.
    
    Uses credentials from api.key file via sg_auth module.
    
    Returns:
        Authenticated shotgun_api3.Shotgun instance
    """
    return getShotgridConnection()


def lookupEntity(code, showCode="lbp3"):
    """Lookup shot, asset, or version in ShotGrid by code.

    Tries in order:
    1. Shot (code contains query)
    2. Asset (code contains query)
    3. Version (numeric ID)

    Args:
        code: Shot/asset code or version ID
        showCode: Show code (default: lbp3, one Space = one show)

    Returns:
        dict: {
            'found': bool,
            'type': 'Shot'|'Asset'|'Version'|None,
            'id': int or None,
            'code': str or None,
            'status': str or None,
            'link': str or None,
            'isOutOfDate': bool (for pipeline issues)
        }
    """
    sg = getSgToken()

    result = {
        'found': False,
        'type': None,
        'id': None,
        'code': None,
        'status': None,
        'link': None,
        'isOutOfDate': False
    }

    try:
        shotResult = sg.find_one(
            "Shot",
            [["code", "contains", code]],
            ["code", "id", "sg_status_list"]
        )

        if shotResult:
            result['found'] = True
            result['type'] = 'Shot'
            result['id'] = shotResult['id']
            result['code'] = shotResult['code']
            result['status'] = shotResult.get('sg_status_list')
            result['link'] = f"https://rodeofx.shotgrid.autodesk.com/detail/Shot/{shotResult['id']}"
            return result

        assetResult = sg.find_one(
            "Asset",
            [["code", "contains", code]],
            ["code", "id", "sg_status_list"]
        )

        if assetResult:
            result['found'] = True
            result['type'] = 'Asset'
            result['id'] = assetResult['id']
            result['code'] = assetResult['code']
            result['status'] = assetResult.get('sg_status_list')
            result['link'] = f"https://rodeofx.shotgrid.autodesk.com/detail/Asset/{assetResult['id']}"
            return result

        if code.isdigit():
            versionResult = sg.find_one(
                "Version",
                [["id", "is", int(code)]],
                ["code", "id", "sg_status_list"]
            )

            if versionResult:
                result['found'] = True
                result['type'] = 'Version'
                result['id'] = versionResult['id']
                result['code'] = versionResult['code']
                result['status'] = versionResult.get('sg_status_list')
                result['link'] = f"https://rodeofx.shotgrid.autodesk.com/detail/Version/{versionResult['id']}"
                return result

    except Exception as exc:
        print(f"ShotGrid lookup error: {exc}")

    return result


def getAssetInfo(assetCode, showCode="lbp3"):
    """Get detailed asset information including publish breakdown by department.

    Queries asset entity and latest publishes per department.
    Uses asset_resolver.py for fault-tolerant publish classification.

    Args:
        assetCode: Asset code (e.g., "chrNolmen")
        showCode: Show code (default: lbp3, one Space = one show)

    Returns:
        dict: {
            'found': bool,
            'code': str,
            'type': str (asset type),
            'status': str (asset status),
            'stage': str (asset stage),
            'sg_url': str (ShotGrid detail URL),
            'publishes': {
                'model': {'version': int, 'status': str, 'publish_id': int},
                'texture': {...},
                'shading': {...},
                'rig': {...},
                'groom': {...}
            }
        }

        If not found: {'found': False, 'code': assetCode}
    """
    sg = getSgToken()

    try:
        assetResult = sg.find_one(
            "Asset",
            [["code", "contains", assetCode]],
            ["code", "id", "sg_status_list", "sg_asset_type", "sg_stage"]
        )

        if not assetResult:
            return {'found': False, 'code': assetCode}

        assetId = assetResult['id']
        assetType = assetResult.get('sg_asset_type') or 'Unknown'
        assetStatus = assetResult.get('sg_status_list') or 'unknown'
        assetStage = assetResult.get('sg_stage') or 'Unknown'
        sgUrl = f"https://rodeofx.shotgrid.autodesk.com/detail/Asset/{assetId}"

        deptResults = resolveLatestPerDept(sg, assetId)

        publishesSummary = {}

        for dept, deptInfo in deptResults.items():
            if deptInfo.get('dept_status') == 'available':
                pub = deptInfo.get('publish')
                publishesSummary[dept] = {
                    'version': deptInfo.get('version', 0),
                    'status': pub.get('sg_status_list') if pub else 'unknown',
                    'publish_id': deptInfo.get('publish_id', -1)
                }

        return {
            'found': True,
            'code': assetResult['code'],
            'type': assetType,
            'status': assetStatus,
            'stage': assetStage,
            'sg_url': sgUrl,
            'publishes': publishesSummary
        }

    except Exception as exc:
        print(f"ShotGrid asset info lookup error: {exc}")
        return {'found': False, 'code': assetCode}
