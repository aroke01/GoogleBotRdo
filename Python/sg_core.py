#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Core ShotGrid operations module.

This module contains functions for fetching data from ShotGrid,
crawling dependency trees, and analyzing publish relationships.
"""

import time
import ssl
from typing import List, Optional

from sg_utils import (
    SG_VERSION_FIELDS,
    SG_PUB_FIELDS,
    getIdFromLink,
    expandLinks,
    extractAllPathsFromPublish,
    pathParts
)


class Node:
    """
    Tree node representing a publish in the dependency graph.

    Attributes:
        id: Publish ID
        pub: Publish entity dictionary
        depth: Depth in the tree
        children: List of child Node objects
    """
    __slots__ = ("id", "pub", "depth", "children")

    def __init__(self, publishId, pub, depth):
        """
        Initialize a Node.

        Args:
            publishId: ShotGrid publish ID
            pub: Publish entity dictionary
            depth: Depth level in tree
        """
        self.id = publishId
        self.pub = pub
        self.depth = depth
        self.children = []


def normalizeVersionInput(versionInput):
    """Normalize user supplied version input strings.

    Args:
        versionInput: Raw version identifier string or number

    Returns:
        Trimmed string with comma separators removed when numeric
    """
    versionStr = str(versionInput).strip()
    if "," in versionStr:
        digitsOnly = versionStr.replace(",", "")
        if digitsOnly.isdigit():
            return digitsOnly
    return versionStr


def fetchVersion(sgConnection, versionId, maxRetries=1):
    """
    Fetch a Version entity from ShotGrid by ID with SSL error retry logic.

    Args:
        sgConnection: Authenticated ShotGrid connection
        versionId: Version entity ID
        maxRetries: Maximum number of retry attempts for SSL errors

    Returns:
        Version entity dictionary or None if not found

    Raises:
        RuntimeError: If version not found after retries
    """
    lastError = None
    for attempt in range(maxRetries):
        try:
            version = sgConnection.find_one("Version", [["id", "is", int(versionId)]], SG_VERSION_FIELDS)
            if not version:
                return None
            return version
        except ssl.SSLError as sslErr:
            lastError = sslErr
            if attempt < maxRetries - 1:
                waitTime = 2 ** attempt
                print(f"[SSL ERROR] Attempt {attempt + 1}/{maxRetries} failed for version {versionId}, retrying in {waitTime}s: {sslErr}")
                time.sleep(waitTime)
            else:
                print(f"[SSL ERROR] All {maxRetries} attempts failed for version {versionId}: {sslErr}")
        except Exception as err:
            print(f"[ERROR] Unexpected error fetching version {versionId}: {err}")
            return None
    
    return None


def fetchVersionByName(sgConnection, versionName):
    """
    Fetch a Version entity from ShotGrid by name (code field).

    Args:
        sgConnection: Authenticated ShotGrid connection
        versionName: Version name/code (e.g., "306dtt_1740.lig.creative.main.defPart.v10")

    Returns:
        Version entity dictionary

    Raises:
        RuntimeError: If version not found
    """
    version = sgConnection.find_one("Version", [["code", "is", versionName]], SG_VERSION_FIELDS)
    if not version:
        raise RuntimeError(f"Version with name '{versionName}' not found.")
    return version


def fetchVersionByIdOrName(sgConnection, versionInput):
    """
    Fetch a Version entity from ShotGrid by ID or name.
    
    Automatically detects if input is numeric (ID) or text (name).

    Args:
        sgConnection: Authenticated ShotGrid connection
        versionInput: Version ID (int/str) or version name (str)

    Returns:
        Version entity dictionary

    Raises:
        RuntimeError: If version not found
    """
    # Convert to string and strip whitespace
    versionStr = normalizeVersionInput(versionInput)
    
    # Check if it's numeric (ID)
    if versionStr.isdigit():
        return fetchVersion(sgConnection, int(versionStr))
    else:
        # Try as name first
        try:
            return fetchVersionByName(sgConnection, versionStr)
        except RuntimeError:
            # If name fails and input looks like it could be an ID, try as ID
            try:
                return fetchVersion(sgConnection, int(versionStr))
            except (ValueError, RuntimeError):
                # Re-raise the original name error
                raise RuntimeError(f"Version '{versionStr}' not found (tried both name and ID)")


def getPublishedFilesForVersion(sgConnection, version):
    """
    Get all TankPublishedFile entities linked to a Version.

    Args:
        sgConnection: Authenticated ShotGrid connection
        version: Version entity dictionary

    Returns:
        List of publish entity dictionaries
    """
    tankPubFile = version.get("tank_published_file")
    if tankPubFile:
        ids = []
        if isinstance(tankPubFile, list):
            ids = [getIdFromLink(item) for item in tankPubFile if getIdFromLink(item)]
        else:
            ids = [getIdFromLink(tankPubFile)]
        if ids:
            return sgConnection.find("TankPublishedFile", [["id", "in", ids]], SG_PUB_FIELDS)

    return sgConnection.find(
        "TankPublishedFile",
        [["sg_version", "is", {"type": "Version", "id": version["id"]}]],
        SG_PUB_FIELDS
    )


def fetchPublishById(sgConnection, pubId):
    """
    Fetch a single TankPublishedFile by ID.

    Args:
        sgConnection: Authenticated ShotGrid connection
        pubId: Publish entity ID

    Returns:
        Publish entity dictionary or None
    """
    return sgConnection.find_one("TankPublishedFile", [["id", "is", int(pubId)]], SG_PUB_FIELDS)


def crawlTree(sgConnection, pubIds, direction="upstream", maxDepth=6, filterOldVersions=False, deduplicateGlobally=True, stopAtCameras=False, hideNukeFiles=False):
    """
    Build a forest of dependency trees starting from publish IDs.

    Args:
        sgConnection: Authenticated ShotGrid connection
        pubIds: List of starting publish IDs
        direction: "upstream", "downstream", or "both"
        maxDepth: Maximum depth to crawl
        filterOldVersions: If True, only keep latest version of each asset
        deduplicateGlobally: If True, show each ID only once in entire tree
        stopAtCameras: If True, don't expand camera dependencies (stop at camera)
        hideNukeFiles: If True, filter out Nuke workfiles from results

    Returns:
        List of root Node objects (forest)
    """
    

    cache = {}
    globalSeen = set()

    def batchFetchPublishes(publishIds):
        """Fetch multiple publishes in a single API call."""
        if not publishIds:
            return
        idsToFetch = [pid for pid in publishIds if pid not in cache]
        if not idsToFetch:
            return
        
        pubs = sgConnection.find(
            'TankPublishedFile',
            [['id', 'in', idsToFetch]],
            SG_PUB_FIELDS,
            limit=500
        )
        
        for pub in pubs:
            if pub:
                cache[pub['id']] = pub

    def fetchCached(publishId):
        """Fetch publish from cache."""
        return cache.get(publishId)

    def expandDirection(pub, directionType):
        """Get next level IDs based on direction."""
        if directionType in ("downstream", "both"):
            for nextId in expandLinks(pub.get("downstream_tank_published_files")):
                yield nextId
        if directionType in ("upstream", "both"):
            for nextId in expandLinks(pub.get("upstream_tank_published_files")):
                yield nextId

    def getAssetKey(pub):
        """Get unique key for asset (name without version)."""
        name = pub.get("name") or pub.get("code") or ""
        tankType = (pub.get("tank_type") or {}).get("name") or ""
        return (name, tankType)

    def filterLatestVersions(childIds):
        """Keep only latest version of each asset."""
        if not filterOldVersions:
            return childIds

        assetGroups = {}
        for childId in childIds:
            childPub = fetchCached(childId)
            if not childPub:
                continue
            key = getAssetKey(childPub)
            version = childPub.get("version_number", 0)
            if key not in assetGroups or version > assetGroups[key][1]:
                assetGroups[key] = (childId, version)

        return [childId for childId, _ in assetGroups.values()]

    def collectAllIds(publishIds, currentDepth):
        """Collect all publish IDs at current depth level."""
        if currentDepth > maxDepth:
            return set()
        
        allIds = set(publishIds)
        for pubId in publishIds:
            pub = fetchCached(pubId)
            if pub:
                childIds = list(expandDirection(pub, direction))
                allIds.update(childIds)
        return allIds

    batchFetchPublishes(pubIds)
    
    for depth in range(maxDepth):
        currentLevelIds = set()
        for pubId in list(cache.keys()):
            pub = cache[pubId]
            if pub:
                childIds = list(expandDirection(pub, direction))
                currentLevelIds.update(childIds)
        
        if not currentLevelIds:
            break
        
        batchFetchPublishes(list(currentLevelIds))

    def buildNode(publishId, depth, pathStackIds):
        """Recursively build tree node."""
        pub = fetchCached(publishId)
        if not pub:
            return None
        
        if deduplicateGlobally:
            if publishId in globalSeen:
                return None
            globalSeen.add(publishId)
        
        if hideNukeFiles:
            tankType = (pub.get("tank_type") or {}).get("name") or ""
            name = pub.get("name") or ""
            if "workfile" in tankType.lower() and (".nk" in name or "nuke" in name.lower()):
                return None
        
        node = Node(publishId, pub, depth)
        
        if depth >= maxDepth:
            return node
        
        if stopAtCameras:
            tankType = (pub.get("tank_type") or {}).get("name") or ""
            if "camera" in tankType.lower():
                return node

        childIds = list(expandDirection(pub, direction))
        childIds = [cid for cid in childIds if cid not in pathStackIds]
        childIds = filterLatestVersions(childIds)

        for nextId in childIds:
            child = buildNode(nextId, depth + 1, pathStackIds | {nextId})
            if child:
                node.children.append(child)
        return node

    forest = []
    for startId in pubIds:
        root = buildNode(startId, 0, {startId})
        if root:
            forest.append(root)
    
    return forest


def findNukeWorkfileUpstream(sgConnection, precompPub):
    """
    Find the NUKE workfile upstream of a precomp publish.

    Args:
        sgConnection: Authenticated ShotGrid connection
        precompPub: Precomp publish entity dictionary

    Returns:
        NUKE workfile publish dictionary or None
    """
    if not precompPub or not precompPub.get("upstream_tank_published_files"):
        return None

    upIds = expandLinks(precompPub["upstream_tank_published_files"])
    if not upIds:
        return None

    upstreamPubs = sgConnection.find("TankPublishedFile", [["id", "in", upIds]], SG_PUB_FIELDS)

    nukeCandidates = []
    for pub in upstreamPubs:
        tankType = (pub.get("tank_type") or {}).get("name") or ""
        if "workfile" in tankType.lower():
            paths = extractAllPathsFromPublish(pub)
            for path in paths:
                if path.endswith(".nk"):
                    nukeCandidates.append(pub)
                    break

    if not nukeCandidates:
        return None

    mainCandidates = [pub for pub in nukeCandidates if "main" in (pub.get("name") or "").lower()]
    candidates = mainCandidates if mainCandidates else nukeCandidates

    candidates.sort(key=lambda pub: pub.get("version_number", 0), reverse=True)
    return candidates[0]


def findRenderUpstream(sgConnection, precompPub):
    """
    Find the render publish upstream of a precomp publish.

    Args:
        sgConnection: Authenticated ShotGrid connection
        precompPub: Precomp publish entity dictionary

    Returns:
        Render publish dictionary or None
    """
    if not precompPub or not precompPub.get("upstream_tank_published_files"):
        return None

    upIds = expandLinks(precompPub["upstream_tank_published_files"])
    if not upIds:
        return None

    upstreamPubs = sgConnection.find("TankPublishedFile", [["id", "in", upIds]], SG_PUB_FIELDS)

    renderCandidates = []
    for pub in upstreamPubs:
        tankType = (pub.get("tank_type") or {}).get("name") or ""
        if "render" in tankType.lower():
            renderCandidates.append(pub)

    if not renderCandidates:
        return None

    mainCandidates = [pub for pub in renderCandidates if "main" in (pub.get("name") or "").lower()]
    candidates = mainCandidates if mainCandidates else renderCandidates

    candidates.sort(key=lambda pub: pub.get("version_number", 0), reverse=True)
    return candidates[0]


def collectAllUpstreamWorkfiles(sgConnection, renderPub, maxDepth=4):
    """
    Collect all workfile publishes upstream of a render publish.

    Args:
        sgConnection: Authenticated ShotGrid connection
        renderPub: Render publish entity dictionary
        maxDepth: Maximum crawl depth

    Returns:
        List of workfile publish dictionaries
    """
    if not renderPub:
        return []

    workfiles = []
    visited = set()

    def crawl(pub, depth):
        """Recursively crawl upstream for workfiles."""
        if depth > maxDepth or pub["id"] in visited:
            return
        visited.add(pub["id"])

        tankType = (pub.get("tank_type") or {}).get("name") or ""
        if "workfile" in tankType.lower():
            workfiles.append(pub)

        upIds = expandLinks(pub.get("upstream_tank_published_files"))
        if upIds:
            upstreamPubs = sgConnection.find("TankPublishedFile", [["id", "in", upIds]], SG_PUB_FIELDS)
            for upPub in upstreamPubs:
                crawl(upPub, depth + 1)

    crawl(renderPub, 0)
    return workfiles


def rankWorkfileCandidates(workfiles, shotCode):
    """
    Rank workfile candidates to pick the best source work file.

    Args:
        workfiles: List of workfile publish dictionaries
        shotCode: Shot code string for matching

    Returns:
        Tuple of (filename, path) or None
    """
    if not workfiles:
        return None

    candidates = []
    for pub in workfiles:
        paths = extractAllPathsFromPublish(pub)
        if not paths:
            continue

        for path in paths:
            pathInfo = pathParts(path)

            shotHit = shotCode in pathInfo.clean

            appPriority = 3
            if "houdini" in pathInfo.clean.lower():
                appPriority = 0
            elif "maya" in pathInfo.clean.lower():
                appPriority = 1
            elif "nuke" in pathInfo.clean.lower():
                appPriority = 2

            versionNum = pub.get("version_number", 0)

            rank = (not shotHit, appPriority, -versionNum, -len(pathInfo.clean))
            candidates.append((rank, pub, pathInfo))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    bestPub, bestPathInfo = candidates[0][1], candidates[0][2]

    from sg_utils import synthesizeFilename
    synthetic = synthesizeFilename(bestPathInfo, bestPub)
    if synthetic:
        return synthetic[0], synthetic[1]

    filename = bestPathInfo.parts.get("filename", "")
    fallbackName = filename or bestPub.get("name") or bestPub.get("code") or "unknown"
    return fallbackName, bestPathInfo.clean
