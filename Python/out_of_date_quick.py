"""Fast out-of-date detection using only description text parsing.

This module provides a quick check for out-of-date assets by parsing the
Version description field only, without expensive manifest/layerStack queries.
"""

import re
from sg_core import fetchVersion


def parseRigVersionsFromDescription(description):
    """Parse rig versions from Version description text.

    Extracts lines like:
    Rig Versions:
     - chrNolmen_001 - chrNolmen.anim.rigVariant0.all_v1
     - prpNolmenStaff_001 - prpNolmenStaff.anim.rigVariant0.all_v3

    Args:
        description: sg_description field from Version entity

    Returns:
        dict mapping assetName to usedVersion number
        Example: {'chrNolmen': 1, 'prpNolmenStaff': 3}
    """
    rigVersions = {}
    
    if not description:
        return rigVersions
    
    # Pattern to match: assetName_NNN - assetName.type.variant.all_vN
    # or: assetName_NNN - vN
    rigPattern = re.compile(r'([a-zA-Z0-9_]+)_\d+\s+-\s+(?:[a-zA-Z0-9_.]+_)?v(\d+)')
    
    inRigSection = False
    for line in description.split('\n'):
        if 'Rig Versions:' in line:
            inRigSection = True
            continue
        
        if inRigSection:
            if line.strip():
                # Stop at next section (starts with [ or *)
                if line.startswith('[') or (line.startswith('*') and line.endswith('*')):
                    break
                
                match = rigPattern.search(line)
                if match:
                    assetName = match.group(1)
                    versionNum = int(match.group(2))
                    rigVersions[assetName] = versionNum
    
    return rigVersions


def getLatestApprovedVersionsForAssets(sg, assetNames, projectId):
    """Get latest approved version for each asset.

    Args:
        sg: ShotGrid connection
        assetNames: list of asset code names
        projectId: Project ID to filter by

    Returns:
        dict mapping assetName to latest approved version number
        Example: {'chrNolmen': 5, 'prpNolmenStaff': 10}
    """
    if not assetNames:
        return {}
    
    # Query assets to get IDs
    assetFilters = [
        ['code', 'in', assetNames],
        ['project.Project.id', 'is', projectId]
    ]
    
    assets = sg.find('Asset', assetFilters, ['id', 'code'])
    assetIdToName = {asset['id']: asset['code'] for asset in assets}
    assetIds = list(assetIdToName.keys())
    
    if not assetIds:
        return {}
    
    # Query latest approved publishes for these assets
    # Focus on rig type since that's what we're tracking
    pubFilters = [
        ['entity.Asset.id', 'in', assetIds],
        ['tank_type.TankType.code', 'in', ['rig', 'geometry', 'model']],
        ['sg_status_list', 'in', ['apr', 'psh']]  # Approved or Pushed
    ]
    
    publishes = sg.find(
        'TankPublishedFile',
        pubFilters,
        ['id', 'entity', 'version_number', 'tank_type'],
        order=[{'field_name': 'version_number', 'direction': 'desc'}]
    )
    
    # Get highest version per asset
    latestVersions = {}
    for pub in publishes:
        entity = pub.get('entity')
        if not entity:
            continue
        
        assetId = entity.get('id')
        assetName = assetIdToName.get(assetId)
        if not assetName:
            continue
        
        versionNum = pub.get('version_number', 0)
        
        # Keep highest version
        if assetName not in latestVersions or versionNum > latestVersions[assetName]:
            latestVersions[assetName] = versionNum
    
    return latestVersions


def quickOutOfDateCheck(sg, versionId):
    """Fast out-of-date check using only description text parsing.

    This is much faster than full analysis because it:
    1. Fetches only the Version record (1 query)
    2. Parses description text (no disk I/O)
    3. Queries latest approved versions (1 query)
    4. Compares versions (in-memory)

    Total: 2 ShotGrid queries vs 15+ for full analysis

    Args:
        sg: ShotGrid connection
        versionId: Version ID to check

    Returns:
        dict with:
            - isOutOfDate: bool - True if any assets are out-of-date
            - assetCount: int - Total assets found in description
            - outOfDateCount: int - Number of out-of-date assets
            - outOfDateAssets: list - Names of out-of-date assets
            - canAnalyze: bool - True if description has rig versions
            - error: str - Error message if check failed
    """
    try:
        # Fetch version (1 SG query) with retries for SSL errors
        version = fetchVersion(sg, versionId, maxRetries=3)
        if not version:
            return {
                "isOutOfDate": False,
                "assetCount": 0,
                "outOfDateCount": 0,
                "outOfDateAssets": [],
                "canAnalyze": False,
                "error": f"Version {versionId} not found"
            }
        
        description = version.get('description', '')
        projectId = version.get('project', {}).get('id')
        
        if not projectId:
            return {
                "isOutOfDate": False,
                "assetCount": 0,
                "outOfDateCount": 0,
                "outOfDateAssets": [],
                "canAnalyze": False,
                "error": "No project ID found"
            }
        
        # Parse rig versions from description (fast, in-memory)
        rigVersions = parseRigVersionsFromDescription(description)
        
        if not rigVersions:
            return {
                "isOutOfDate": False,
                "assetCount": 0,
                "outOfDateCount": 0,
                "outOfDateAssets": [],
                "canAnalyze": False,
                "error": None
            }
        
        # Get latest approved versions (1 SG query)
        assetNames = list(rigVersions.keys())
        latestVersions = getLatestApprovedVersionsForAssets(sg, assetNames, projectId)
        
        # Compare versions (fast, in-memory)
        outOfDateAssets = []
        for assetName, usedVer in rigVersions.items():
            latestVer = latestVersions.get(assetName, 0)
            if latestVer > usedVer:
                outOfDateAssets.append({
                    "name": assetName,
                    "used": usedVer,
                    "latest": latestVer
                })
        
        return {
            "isOutOfDate": len(outOfDateAssets) > 0,
            "assetCount": len(rigVersions),
            "outOfDateCount": len(outOfDateAssets),
            "outOfDateAssets": outOfDateAssets,
            "canAnalyze": True,
            "error": None
        }
        
    except Exception as error:
        print(f"[QUICK-OOD] Error in quickOutOfDateCheck: {error}")
        return {
            "isOutOfDate": False,
            "assetCount": 0,
            "outOfDateCount": 0,
            "outOfDateAssets": [],
            "canAnalyze": False,
            "error": str(error)
        }
