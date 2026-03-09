#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playlist Dependency Viewer Module.

Fetches ShotGrid Playlist data and generates dependency reports for all dailies
in the playlist, showing upstream department chains for coordinator review.
"""

import re
from urllib.parse import unquote

from discovery_approval import buildDailyChainTree, dailyNodeToDict, classifyVersionDepartment
from out_of_date_analysis import analyzeOutOfDateContentComprehensive


def extractPlaylistId(playlistInput):
    """
    Extract playlist ID from number or ShotGrid URL.
    
    Accepts:
    - Plain ID: "232816"
    - URL with hash: "https://rodeofx.shotgrid.autodesk.com/page/1434981?layout=PLAYLISTS#Playlist_232816"
    
    Args:
        playlistInput: String containing playlist ID or full URL
        
    Returns:
        int: Playlist ID
        
    Raises:
        ValueError: If ID cannot be extracted
    """
    if not playlistInput:
        raise ValueError("Playlist input is empty")
    
    inputStr = str(playlistInput).strip()
    
    # Try direct numeric ID
    if inputStr.isdigit():
        return int(inputStr)
    
    # Try extracting from URL hash: #Playlist_232816
    hashMatch = re.search(r'#Playlist[_-](\d+)', inputStr)
    if hashMatch:
        return int(hashMatch.group(1))
    
    # Try extracting from URL parameter: playlist_id=232816 or id=232816
    paramMatch = re.search(r'[?&](?:playlist_)?id=(\d+)', inputStr)
    if paramMatch:
        return int(paramMatch.group(1))
    
    # Try finding any number in the string as last resort
    numberMatch = re.search(r'(\d+)', inputStr)
    if numberMatch:
        return int(numberMatch.group(1))
    
    raise ValueError(f"Could not extract playlist ID from: {playlistInput}")


def fetchPlaylistVersions(sg, playlistId):
    """
    Fetch Playlist entity and all its Versions from ShotGrid.
    
    Args:
        sg: ShotGrid connection
        playlistId: Playlist entity ID
        
    Returns:
        dict: {
            'playlistName': str,
            'description': str,
            'versions': [Version entities in playlist order]
        }
        
    Raises:
        RuntimeError: If playlist not found
    """
    # Query Playlist entity
    playlist = sg.find_one(
        'Playlist',
        [['id', 'is', playlistId]],
        ['code', 'description', 'versions']
    )
    
    if not playlist:
        raise RuntimeError(f"Playlist {playlistId} not found in ShotGrid")
    
    playlistName = playlist.get('code') or f"Playlist {playlistId}"
    description = playlist.get('description') or ''
    
    # Get versions list (already in playlist order)
    versionLinks = playlist.get('versions') or []
    
    if not versionLinks:
        return {
            'playlistName': playlistName,
            'description': description,
            'versions': []
        }
    
    # Extract version IDs
    versionIds = [v.get('id') for v in versionLinks if v.get('id')]
    
    if not versionIds:
        return {
            'playlistName': playlistName,
            'description': description,
            'versions': []
        }
    
    # Fetch full Version entities
    versions = sg.find(
        'Version',
        [['id', 'in', versionIds]],
        [
            'id', 'code', 'entity', 'sg_department', 'sg_status_list',
            'created_at', 'user', 'version_number', 'tank_published_file',
            'description'
        ]
    )
    
    # Restore playlist order (SG find() doesn't preserve order)
    versionById = {v['id']: v for v in versions}
    orderedVersions = []
    for vId in versionIds:
        if vId in versionById:
            orderedVersions.append(versionById[vId])
    
    return {
        'playlistName': playlistName,
        'description': description,
        'versions': orderedVersions
    }


def formatAssetSummary(assetAnalysis):
    """
    Format asset analysis results as compact summary (Option 3 style).
    
    Args:
        assetAnalysis: Result from analyzeOutOfDateContentComprehensive
        
    Returns:
        str: Formatted asset summary or empty string if no assets
    """
    if not assetAnalysis or 'allItems' not in assetAnalysis:
        return ''
    
    allItems = assetAnalysis.get('allItems', [])
    if not allItems:
        return ''
    
    summary = assetAnalysis.get('summary', {})
    totalAssets = summary.get('total', 0)
    outOfDateCount = summary.get('outOfDate', 0)
    
    if totalAssets == 0:
        return ''
    
    lines = []
    lines.append('')
    lines.append(f"Assets: {totalAssets} total, {outOfDateCount} outdated")
    
    # Group by asset
    assetGroups = {}
    for item in allItems:
        assetName = item.get('entityName', 'unknown')
        if assetName not in assetGroups:
            assetGroups[assetName] = []
        assetGroups[assetName].append(item)
    
    # Format each asset with ALL departments
    for assetName in sorted(assetGroups.keys()):
        items = assetGroups[assetName]
        outdatedItems = [i for i in items if i.get('verdict') == 'Out-of-date']
        
        # Show all departments for this asset
        deptParts = []
        for item in items:
            tankType = item.get('tankType', 'unknown')
            usedVer = item.get('usedVersion', '?')
            availableVer = item.get('availableVersion')
            verdict = item.get('verdict', 'Unknown')
            
            if verdict == 'Out-of-date' and availableVer:
                deptParts.append(f"{tankType.lower()} v{usedVer} ⚠ v{availableVer}")
            else:
                deptParts.append(f"{tankType.lower()} v{usedVer} ✓")
        
        icon = "⚠" if outdatedItems else "✓"
        lines.append(f"  {icon} {assetName}: {', '.join(deptParts)}")
    
    return '\n'.join(lines)


def formatDailyAsAsciiTree(dailyNode, depth=0, isLast=True, prefix=''):
    """
    Format a daily chain tree node as ASCII art with QC connections.
    
    Args:
        dailyNode: DailyNode object from buildDailyChainTree
        depth: Current depth level
        isLast: Whether this is the last child at this level
        prefix: Accumulated prefix for indentation
        
    Returns:
        str: ASCII tree representation
    """
    lines = []
    
    # Get version info
    versionData = dailyNode.version
    versionCode = versionData.get('code', 'unknown')
    
    # Extract version from code string (e.g., "v2" from "lay.arsPrecomp.lay.center.v2")
    import re
    versionMatch = re.search(r'\.v(\d+)$|_v(\d+)$', versionCode)
    if versionMatch:
        versionNum = versionMatch.group(1) or versionMatch.group(2)
    else:
        versionNum = '?'
    
    # Classify department (use sg_department field first, then parse from code)
    dept = versionData.get('sg_department')
    deptFromCode, isQc = classifyVersionDepartment(versionCode)
    if not dept:
        dept = deptFromCode
    
    # Build node line
    connector = '└── ' if isLast else '├── '
    deptLabel = f"{dept} QC" if isQc else dept
    nodeLine = f"{prefix}{connector}({deptLabel}, v{versionNum}) {versionCode}"
    
    # Add QC sibling connection if present
    if hasattr(dailyNode, 'qcSibling') and dailyNode.qcSibling:
        qcVer = dailyNode.qcSibling.version
        qcCode = qcVer.get('code', 'unknown')
        nodeLine += f" <---> {qcCode}"
    
    lines.append(nodeLine)
    
    # Process children
    children = dailyNode.children
    for idx, child in enumerate(children):
        isLastChild = (idx == len(children) - 1)
        childPrefix = prefix + ('    ' if isLast else '│   ')
        childLines = formatDailyAsAsciiTree(child, depth + 1, isLastChild, childPrefix)
        lines.append(childLines)
    
    return '\n'.join(lines)


def buildPlaylistDependencyReport(sg, playlistId, includeAssets=False):
    """
    Build complete dependency report for all dailies in a playlist.
    
    Args:
        sg: ShotGrid connection
        playlistId: Playlist entity ID
        includeAssets: Whether to include asset analysis (default True)
        
    Returns:
        dict: {
            'playlistName': str,
            'description': str,
            'totalDailies': int,
            'dailies': [{
                'versionId': int,
                'versionCode': str,
                'shotCode': str,
                'department': str,
                'asciiTree': str
            }]
        }
    """
    import time
    
    startTime = time.time()
    
    # Fetch playlist and versions
    playlistData = fetchPlaylistVersions(sg, playlistId)
    fetchTime = time.time() - startTime
    print(f"[PLAYLIST TIMING] Fetch playlist: {fetchTime:.2f}s")
    
    playlistName = playlistData['playlistName']
    description = playlistData['description']
    versions = playlistData['versions']
    
    dailies = []
    hierarchyTotalTime = 0
    assetTotalTime = 0
    
    for idx, version in enumerate(versions, 1):
        versionId = version.get('id')
        versionCode = version.get('code', 'unknown')
        
        print(f"[PLAYLIST] Processing daily {idx}/{len(versions)}: {versionCode}")
        
        # Extract shot code from entity
        entity = version.get('entity') or {}
        shotCode = entity.get('name') or entity.get('code') or 'unknown'
        
        # Get department (use sg_department field first, then parse from code)
        dept = version.get('sg_department')
        deptFromCode, isQc = classifyVersionDepartment(versionCode)
        if not dept:
            dept = deptFromCode
        department = f"{dept} QC" if isQc else dept
        
        # Build dependency tree for this daily
        hierarchyStart = time.time()
        try:
            dailyTree = buildDailyChainTree(sg, versionId, maxDepth=10)
            
            # Format as ASCII
            if dailyTree:
                asciiTree = formatDailyAsAsciiTree(dailyTree)
            else:
                asciiTree = f"└── ({department}, v{version.get('version_number', '?')}) {versionCode}\n    (No upstream dependencies found)"
        except Exception as ex:
            print(f"[ERROR] Failed to build tree for version {versionId}: {ex}")
            asciiTree = f"└── ({department}, v{version.get('version_number', '?')}) {versionCode}\n    (Error building dependency tree)"
        
        hierarchyTime = time.time() - hierarchyStart
        hierarchyTotalTime += hierarchyTime
        
        # Analyze assets in this shot (Phase 2) - optional
        assetSummary = ''
        if includeAssets:
            assetStart = time.time()
            try:
                assetAnalysis = analyzeOutOfDateContentComprehensive(sg, versionId)
                assetSummary = formatAssetSummary(assetAnalysis)
            except Exception as ex:
                print(f"[ERROR] Failed to analyze assets for version {versionId}: {ex}")
            assetTime = time.time() - assetStart
            assetTotalTime += assetTime
        
        dailies.append({
            'versionId': versionId,
            'versionCode': versionCode,
            'shotCode': shotCode,
            'department': department,
            'asciiTree': asciiTree,
            'assetSummary': assetSummary
        })
    
    totalTime = time.time() - startTime
    print(f"[PLAYLIST TIMING] Total: {totalTime:.2f}s")
    print(f"[PLAYLIST TIMING] Hierarchy (all dailies): {hierarchyTotalTime:.2f}s")
    if includeAssets:
        print(f"[PLAYLIST TIMING] Assets (all dailies): {assetTotalTime:.2f}s")
    
    return {
        'playlistName': playlistName,
        'description': description,
        'totalDailies': len(dailies),
        'dailies': dailies
    }
