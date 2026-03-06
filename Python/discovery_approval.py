#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Approval Hierarchy Discovery Script.

Run this script to discover the actual ShotGrid data structure for a given Shot.
This will help us understand:
- What department values exist (sg_department)
- What status values are used (sg_status_list)
- What tank_type names represent QC caches
- Whether upstream/downstream links are populated

Usage:
    python discovery_approval.py --shot-id 12345
    python discovery_approval.py --shot-code "13ta_1280"
    python discovery_approval.py --version-code "312ljn_2380.lig.creative.main.defPart.v6"
    python discovery_approval.py --version-id 67890
"""

import argparse
import json
import os
import re
import ssl
import sys
import time
from collections import defaultdict
from datetime import datetime

from sg_auth import getShotgridConnection
from sg_utils import buildShotgridUrl, buildMediaCenterUrl


# Approval hierarchy constants
# Pipeline order (typical VFX flow)
DEPARTMENTS = [
    'Plate', 'Editorial', 'CMM', 'Layout', 'Anim', 'Crowd', 'CFX', 'FX',
    'Lighting', 'ENV', 'MP', 'Roto', 'Comp',
]

# Status values that indicate approval
# apr = Approved, psh = Pushed (approved and sent downstream)
STATUS_APPROVED = {'apr', 'psh'}

# Status values that indicate delivery (final output)
STATUS_DELIVERED = {'dlvr'}

# Status values that indicate completion (but not necessarily approved)
STATUS_COMPLETE = {'cmpt'}

# Status values that indicate work in progress
STATUS_PENDING = {'vwd', 'na', 'rev', 'arev', 'supr', 'fxsupr'}

# Status values that indicate rejected/void
STATUS_REJECTED = {'void'}

# Version naming patterns per department
# QC versions: {shot}.qc{dept}.primary.main.defPart.v{N}
# Regular dailies: {shot}.{dept}.{task}.{variant}.defPart.v{N}
# ARS precomp: {shot}.{dept}.arsPrecomp.{variant}.center.v{N}
#
# Examples discovered:
#   Layout QC: 306dtt_1380.qclay.primary.main.defPart.v3
#   Layout daily: 101029_0020.lay.arsPrecomp.lay.center.v3
#   Anim QC: 306dtt_1380.qcani.primary.main.defPart.v2
#   Anim daily: 091ss_8780.ani.ars.staging.center.v9
#   Lighting: 13ta_1280.lig.primary.main.defPart.v25
#   Comp: 13ta_1280.comp.render.comp.v24
#   Comp QC: 162_0002.qccomp.render.comp_qc.v1
#   Crowd: 506bob_0520.crw.arsPrecomp.crowdSim.center.v1
#   Crowd QC: 506bob_0510.qccrw.primary.main.defPart.v6
#   CFX: 503bcd_1290.cfx.flipbook.DdNightingale_clothNhair.main.v1
#   CFX QC: 309053_0400.qccfx.primary.main.defPart.v2
#   FX: 086ss_7915.fx.fxSmokeTrail.main.defPart.v12
DEPT_VERSION_PATTERNS = {
    'CMM': [],
    'Layout': ['qclay', '.lay.'],
    'Anim': ['qcani', '.ani.'],
    'Crowd': ['qccrw', '.crw.'],
    'CFX': ['qccfx', '.cfx.'],
    'FX': ['.fx.'],
    'Lighting': ['.lig.'],
    'Comp': ['qccomp', '.comp.']
}

# Handover types per department (caches that flow between depts)
HANDOVER_TYPES = {
    'CMM': ['camera', 'usdLayerStack'],
    'Layout': ['camera', 'usdLayerStack'],
    'Anim': ['deformedGeometry', 'animation.atom'],
    'CFX': ['deformedGeometry'],
    'FX': ['render'],
    'Lighting': ['render'],
    'Comp': ['precomp', 'render']
}


def extractShotCodeFromVersionCode(versionCode):
    """
    Extract shot code from a version code.

    Version codes follow pattern: {shot}.{dept}.{task}.{variant}.v{N}
    Examples:
        312ljn_2380.lig.creative.main.defPart.v6 -> 312ljn_2380
        306dtt_1380.qclay.primary.main.defPart.v3 -> 306dtt_1380

    Args:
        versionCode: Full version code string

    Returns:
        Shot code string (first segment before first dot)
    """
    if not versionCode:
        return None
    return versionCode.split('.')[0]


def extractVersionFromCode(code):
    """
    Extract version number from a version code.

    Args:
        code: Version code string like 'shot.dept.task.v2'

    Returns:
        Version number as integer, or None if not found
    """
    match = re.search(r'[._]v(\d+)', code, re.IGNORECASE)
    return int(match.group(1)) if match else None


def normalizeNumericId(rawValue):
    """Normalize numeric IDs copied from ShotGrid UI.

    Args:
        rawValue: Raw ID value that may contain comma separators

    Returns:
        Integer ID or None if the input is invalid
    """
    if rawValue is None:
        return None
    valueStr = str(rawValue).strip().replace(',', '')
    return int(valueStr) if valueStr.isdigit() else None


def discoverFromShot(sg, shotId):
    """
    Run all discovery queries for a given Shot ID.

    Args:
        sg: ShotGrid connection
        shotId: Shot entity ID

    Returns:
        Dictionary with all discovery results
    """
    results = {
        "shot_id": shotId,
        "shot_info": None,
        "versions": {
            "total": 0,
            "by_department": {},
            "by_status": {},
            "department_values": set(),
            "status_values": set(),
            "sample_codes": []
        },
        "published_files": {
            "total": 0,
            "by_tank_type": {},
            "by_status": {},
            "tank_type_values": set(),
            "status_values": set(),
            "with_upstream": 0,
            "with_downstream": 0
        },
        "potential_handovers": [],
        "raw_samples": {
            "versions": [],
            "published_files": []
        }
    }

    # Get Shot info
    print(f"\n[1/4] Fetching Shot info...")
    shot = sg.find_one(
        "Shot",
        [["id", "is", shotId]],
        ["code", "sg_sequence", "project", "sg_status_list"]
    )
    if not shot:
        print(f"ERROR: Shot ID {shotId} not found")
        return None
    results["shot_info"] = shot
    print(f"  Shot: {shot.get('code')}")

    # Get all Versions for this Shot
    print(f"\n[2/4] Fetching Versions...")
    versions = sg.find(
        "Version",
        [["entity", "is", {"type": "Shot", "id": shotId}]],
        [
            "code",
            "sg_department",
            "sg_status_list",
            "created_at",
            "user",
            "tank_published_file"
        ],
        order=[{"field_name": "created_at", "direction": "desc"}],
        limit=200
    )
    results["versions"]["total"] = len(versions)
    print(f"  Found {len(versions)} Versions")

    for ver in versions:
        dept = ver.get("sg_department") or "NONE"
        status = ver.get("sg_status_list") or "NONE"

        results["versions"]["department_values"].add(dept)
        results["versions"]["status_values"].add(status)
        results["versions"]["by_department"][dept] = results["versions"]["by_department"].get(dept, 0) + 1
        results["versions"]["by_status"][status] = results["versions"]["by_status"].get(status, 0) + 1

    results["versions"]["sample_codes"] = [v.get("code") for v in versions[:10]]
    results["raw_samples"]["versions"] = versions[:5]

    # Get all PublishedFiles for this Shot
    print(f"\n[3/4] Fetching PublishedFiles...")
    pubs = sg.find(
        "TankPublishedFile",
        [["entity", "is", {"type": "Shot", "id": shotId}]],
        [
            "code",
            "name",
            "tank_type",
            "sg_status_list",
            "created_at",
            "created_by",
            "upstream_tank_published_files",
            "downstream_tank_published_files",
            "version_number"
        ],
        order=[{"field_name": "created_at", "direction": "desc"}],
        limit=500
    )
    results["published_files"]["total"] = len(pubs)
    print(f"  Found {len(pubs)} PublishedFiles")

    for pub in pubs:
        tankType = (pub.get("tank_type") or {}).get("name") or "NONE"
        status = pub.get("sg_status_list") or "NONE"
        upstream = pub.get("upstream_tank_published_files") or []
        downstream = pub.get("downstream_tank_published_files") or []

        results["published_files"]["tank_type_values"].add(tankType)
        results["published_files"]["status_values"].add(status)
        results["published_files"]["by_tank_type"][tankType] = results["published_files"]["by_tank_type"].get(tankType, 0) + 1
        results["published_files"]["by_status"][status] = results["published_files"]["by_status"].get(status, 0) + 1

        if upstream:
            results["published_files"]["with_upstream"] += 1
        if downstream:
            results["published_files"]["with_downstream"] += 1

        # Identify potential handover types (have "qc" in name or specific patterns)
        nameLower = (pub.get("name") or "").lower()
        tankLower = tankType.lower()
        if "qc" in tankLower or "cache" in tankLower or "qc" in nameLower:
            results["potential_handovers"].append({
                "name": pub.get("name"),
                "tank_type": tankType,
                "status": status,
                "has_upstream": len(upstream) > 0,
                "has_downstream": len(downstream) > 0
            })

    results["raw_samples"]["published_files"] = pubs[:5]

    # Find approved versions per department
    print(f"\n[4/4] Finding approved Versions per department...")
    results["approved_per_department"] = {}
    for dept in results["versions"]["department_values"]:
        if dept == "NONE":
            continue
        approved = sg.find(
            "Version",
            [
                ["entity", "is", {"type": "Shot", "id": shotId}],
                ["sg_department", "is", dept],
                ["sg_status_list", "in", ["apr", "approved", "pushed", "pub", "final"]]
            ],
            ["code", "sg_status_list", "created_at"],
            order=[{"field_name": "created_at", "direction": "desc"}],
            limit=3
        )
        results["approved_per_department"][dept] = [
            {"code": v.get("code"), "status": v.get("sg_status_list")}
            for v in approved
        ]
        print(f"  {dept}: {len(approved)} approved")

    # Convert sets to lists for JSON serialization
    results["versions"]["department_values"] = sorted(list(results["versions"]["department_values"]))
    results["versions"]["status_values"] = sorted(list(results["versions"]["status_values"]))
    results["published_files"]["tank_type_values"] = sorted(list(results["published_files"]["tank_type_values"]))
    results["published_files"]["status_values"] = sorted(list(results["published_files"]["status_values"]))

    return results


def discoverFromVersion(sg, versionId):
    """
    Run discovery starting from a specific Version ID.
    Traces upstream dependencies.

    Args:
        sg: ShotGrid connection
        versionId: Version entity ID

    Returns:
        Dictionary with discovery results
    """
    results = {
        "version_id": versionId,
        "version_info": None,
        "shot_id": None,
        "dependency_chain": [],
        "chain_depth": 0
    }

    print(f"\n[1/3] Fetching Version info...")
    version = sg.find_one(
        "Version",
        [["id", "is", versionId]],
        [
            "code",
            "sg_department",
            "sg_status_list",
            "entity",
            "tank_published_file",
            "created_at",
            "user"
        ]
    )
    if not version:
        print(f"ERROR: Version ID {versionId} not found")
        return None

    results["version_info"] = {
        "code": version.get("code"),
        "department": version.get("sg_department"),
        "status": version.get("sg_status_list"),
        "entity": version.get("entity")
    }
    print(f"  Version: {version.get('code')}")
    print(f"  Department: {version.get('sg_department')}")
    print(f"  Status: {version.get('sg_status_list')}")

    entity = version.get("entity")
    if entity and entity.get("type") == "Shot":
        results["shot_id"] = entity.get("id")
        print(f"  Shot ID: {results['shot_id']}")

    # Get linked PublishedFiles
    linkedPubs = version.get("tank_published_file") or []
    if not linkedPubs:
        print("  No linked PublishedFiles found")
        return results

    print(f"\n[2/3] Tracing upstream dependencies...")
    pubIds = [p["id"] for p in linkedPubs]

    # Recursive trace (limited depth)
    visited = set()
    toProcess = pubIds
    depth = 0
    maxDepth = 6

    while toProcess and depth < maxDepth:
        depth += 1
        print(f"  Depth {depth}: Processing {len(toProcess)} items...")

        pubs = sg.find(
            "TankPublishedFile",
            [["id", "in", toProcess]],
            [
                "name",
                "tank_type",
                "sg_status_list",
                "upstream_tank_published_files",
                "created_by",
                "version_number"
            ]
        )

        nextBatch = []
        for pub in pubs:
            if pub["id"] in visited:
                continue
            visited.add(pub["id"])

            tankType = (pub.get("tank_type") or {}).get("name") or "unknown"
            upstream = pub.get("upstream_tank_published_files") or []

            results["dependency_chain"].append({
                "depth": depth,
                "id": pub["id"],
                "name": pub.get("name"),
                "tank_type": tankType,
                "status": pub.get("sg_status_list"),
                "upstream_count": len(upstream)
            })

            for upPub in upstream:
                upId = upPub.get("id")
                if upId and upId not in visited:
                    nextBatch.append(upId)

        toProcess = nextBatch

    results["chain_depth"] = depth
    print(f"  Total items in chain: {len(results['dependency_chain'])}")

    # Run full shot discovery if we found a shot
    if results["shot_id"]:
        print(f"\n[3/3] Running full Shot discovery...")
        shotResults = discoverFromShot(sg, results["shot_id"])
        if shotResults:
            results["shot_discovery"] = shotResults

            # Also run approval hierarchy discovery
            shotCode = shotResults.get("shot_info", {}).get("code")
            if shotCode:
                approvalResults = discoverApprovalHierarchy(sg, results["shot_id"], shotCode)
                results["approval_hierarchy"] = approvalResults

    return results


def findShotByCode(sg, shotCode):
    """
    Find Shot ID by code.

    Args:
        sg: ShotGrid connection
        shotCode: Shot code string

    Returns:
        Shot ID or None
    """
    shot = sg.find_one(
        "Shot",
        [["code", "is", shotCode]],
        ["id", "code"]
    )
    if shot:
        return shot["id"]

    # Try contains search
    shots = sg.find(
        "Shot",
        [["code", "contains", shotCode]],
        ["id", "code"],
        limit=5
    )
    if shots:
        print(f"Found {len(shots)} shots matching '{shotCode}':")
        for shot in shots:
            print(f"  - {shot['code']} (ID: {shot['id']})")
        return shots[0]["id"]

    return None


def printSummary(results):
    """
    Print a human-readable summary of discovery results.

    Args:
        results: Discovery results dictionary
    """
    print("\n" + "=" * 60)
    print("DISCOVERY SUMMARY")
    print("=" * 60)

    if results.get("shot_info"):
        print(f"\nShot: {results['shot_info'].get('code')}")

    if results.get("versions"):
        ver = results["versions"]
        print(f"\n--- VERSIONS ({ver['total']} total) ---")
        print(f"Department values found: {ver['department_values']}")
        print(f"Status values found: {ver['status_values']}")
        print("\nBy Department:")
        for dept, count in sorted(ver["by_department"].items(), key=lambda x: -x[1]):
            print(f"  {dept}: {count}")
        print("\nBy Status:")
        for status, count in sorted(ver["by_status"].items(), key=lambda x: -x[1]):
            print(f"  {status}: {count}")

    if results.get("published_files"):
        pub = results["published_files"]
        print(f"\n--- PUBLISHED FILES ({pub['total']} total) ---")
        print(f"Tank type values found: {pub['tank_type_values']}")
        print(f"Status values found: {pub['status_values']}")
        print(f"With upstream links: {pub['with_upstream']} ({100*pub['with_upstream']//max(1,pub['total'])}%)")
        print(f"With downstream links: {pub['with_downstream']} ({100*pub['with_downstream']//max(1,pub['total'])}%)")
        print("\nBy Tank Type:")
        for tankType, count in sorted(pub["by_tank_type"].items(), key=lambda x: -x[1]):
            print(f"  {tankType}: {count}")

    if results.get("potential_handovers"):
        print(f"\n--- POTENTIAL HANDOVER TYPES ---")
        seen = set()
        for item in results["potential_handovers"]:
            key = item["tank_type"]
            if key not in seen:
                seen.add(key)
                print(f"  {key}")

    if results.get("approved_per_department"):
        print(f"\n--- APPROVED VERSIONS PER DEPARTMENT ---")
        for dept, versions in results["approved_per_department"].items():
            if versions:
                print(f"  {dept}: {versions[0]['code']} ({versions[0]['status']})")
            else:
                print(f"  {dept}: NONE FOUND")

    if results.get("dependency_chain"):
        print(f"\n--- DEPENDENCY CHAIN (from Version) ---")
        print(f"Total items: {len(results['dependency_chain'])}")
        print(f"Max depth: {results['chain_depth']}")
        print("\nTypes in chain:")
        typeCount = defaultdict(int)
        for item in results["dependency_chain"]:
            typeCount[item["tank_type"]] += 1
        for tankType, count in sorted(typeCount.items(), key=lambda x: -x[1]):
            print(f"  {tankType}: {count}")

    # Print approval hierarchy if available
    if results.get("approval_hierarchy"):
        hierarchy = results["approval_hierarchy"]["hierarchy"]
        shotCode = results.get("shot_info", {}).get("code", "Unknown")
        printApprovalHierarchy(hierarchy, shotCode)


def findDeptVersionsForShot(sg, shotId, shotCode):
    """
    Find all department versions for a shot, organized by department.

    Searches for both QC versions (qclay, qcani) and regular dailies
    (.lig., .comp.) depending on department patterns.

    Args:
        sg: ShotGrid connection
        shotId: Shot entity ID
        shotCode: Shot code string

    Returns:
        Dictionary mapping department to list of versions
    """
    deptVersions = {dept: [] for dept in DEPARTMENTS}
    seenIds = set()

    for dept, patterns in DEPT_VERSION_PATTERNS.items():
        if dept == 'CMM':
            versions = sg.find(
                "Version",
                [
                    ["entity", "is", {"type": "Shot", "id": shotId}],
                    ["sg_department", "is", "CMM"],
                ],
                [
                    "code",
                    "sg_department",
                    "sg_status_list",
                    "created_at",
                    "user",
                    "tank_published_file",
                    "version_number",
                    "description",
                    "sg_path_to_movie",
                    "sg_uploaded_movie",
                    "image",
                    "entity",
                ],
                order=[{"field_name": "created_at", "direction": "desc"}],
                limit=30,
            )

            for ver in versions:
                if ver["id"] in seenIds:
                    continue

                seenIds.add(ver["id"])
                deptVersions[dept].append({
                    "id": ver["id"],
                    "code": ver.get("code") or "",
                    "department": ver.get("sg_department"),
                    "status": ver.get("sg_status_list"),
                    "created_at": ver.get("created_at"),
                    "user": (ver.get("user") or {}).get("name"),
                    "version_number": ver.get("version_number"),
                    "description": ver.get("description"),
                    "sg_path_to_movie": ver.get("sg_path_to_movie"),
                    "sg_uploaded_movie": ver.get("sg_uploaded_movie"),
                    "image": ver.get("image"),
                    "entity": ver.get("entity"),
                    "tank_published_file": ver.get("tank_published_file"),
                    "is_approved": ver.get("sg_status_list") in STATUS_APPROVED,
                    "is_delivered": ver.get("sg_status_list") in STATUS_DELIVERED,
                    "is_qc": False,
                    "pattern_matched": "sg_department=CMM",
                })

            deptVersions[dept].sort(
                key=lambda item: item.get("created_at") or "",
                reverse=True,
            )
            continue

        for pattern in patterns:
            # Search for versions containing this pattern
            versions = sg.find(
                "Version",
                [
                    ["entity", "is", {"type": "Shot", "id": shotId}],
                    ["code", "contains", pattern]
                ],
                [
                    "code",
                    "sg_department",
                    "sg_status_list",
                    "created_at",
                    "user",
                    "tank_published_file",
                    "version_number",
                    "description",
                    "sg_path_to_movie",
                    "sg_uploaded_movie",
                    "image",
                    "entity"
                ],
                order=[{"field_name": "created_at", "direction": "desc"}],
                limit=30
            )

            # Filter to actual matches and avoid duplicates
            for ver in versions:
                if ver["id"] in seenIds:
                    continue

                code = ver.get("code") or ""
                codeLower = code.lower()

                # Verify pattern actually matches
                if pattern.lower() not in codeLower:
                    continue

                seenIds.add(ver["id"])
                isQc = pattern.startswith("qc")

                deptVersions[dept].append({
                    "id": ver["id"],
                    "code": code,
                    "department": ver.get("sg_department"),
                    "status": ver.get("sg_status_list"),
                    "created_at": ver.get("created_at"),
                    "user": (ver.get("user") or {}).get("name"),
                    "version_number": ver.get("version_number"),
                    "description": ver.get("description"),
                    "sg_path_to_movie": ver.get("sg_path_to_movie"),
                    "sg_uploaded_movie": ver.get("sg_uploaded_movie"),
                    "image": ver.get("image"),
                    "entity": ver.get("entity"),
                    "tank_published_file": ver.get("tank_published_file"),
                    "is_approved": ver.get("sg_status_list") in STATUS_APPROVED,
                    "is_delivered": ver.get("sg_status_list") in STATUS_DELIVERED,
                    "is_qc": isQc,
                    "pattern_matched": pattern
                })

        # Sort by created_at descending (most recent first)
        deptVersions[dept].sort(
            key=lambda x: x.get("created_at") or "",
            reverse=True
        )

    fallbackDepartments = ['Crowd', 'CFX', 'FX']
    for deptName in fallbackDepartments:
        if deptVersions.get(deptName):
            continue

        versions = sg.find(
            "Version",
            [
                ["entity", "is", {"type": "Shot", "id": shotId}],
                ["sg_department", "is", deptName],
            ],
            [
                "code",
                "sg_department",
                "sg_status_list",
                "created_at",
                "user",
                "tank_published_file",
                "version_number",
                "description",
                "sg_path_to_movie",
                "sg_uploaded_movie",
                "image",
                "entity",
            ],
            order=[{"field_name": "created_at", "direction": "desc"}],
            limit=30,
        )

        for ver in (versions or []):
            verId = ver.get('id')
            if not verId or verId in seenIds:
                continue

            code = ver.get("code") or ""
            _, isQc = classifyVersionDepartment(code)

            seenIds.add(verId)
            deptVersions[deptName].append({
                "id": verId,
                "code": code,
                "department": ver.get("sg_department"),
                "status": ver.get("sg_status_list"),
                "created_at": ver.get("created_at"),
                "user": (ver.get("user") or {}).get("name"),
                "version_number": ver.get("version_number"),
                "description": ver.get("description"),
                "sg_path_to_movie": ver.get("sg_path_to_movie"),
                "sg_uploaded_movie": ver.get("sg_uploaded_movie"),
                "image": ver.get("image"),
                "entity": ver.get("entity"),
                "tank_published_file": ver.get("tank_published_file"),
                "is_approved": ver.get("sg_status_list") in STATUS_APPROVED,
                "is_delivered": ver.get("sg_status_list") in STATUS_DELIVERED,
                "is_qc": isQc,
                "pattern_matched": f"sg_department={deptName}",
            })

        deptVersions[deptName].sort(
            key=lambda item: item.get("created_at") or "",
            reverse=True,
        )

    return deptVersions


def buildApprovalHierarchy(deptVersions):
    """
    Build approval hierarchy from department versions.

    Args:
        deptVersions: Dictionary from findDeptVersionsForShot

    Returns:
        List of dictionaries with approval status per department
    """
    hierarchy = []

    for dept in DEPARTMENTS:
        versions = deptVersions.get(dept, [])

        if not versions:
            hierarchy.append({
                "department": dept,
                "status": "no_versions",
                "status_display": "No Versions",
                "latest_version": None,
                "approved_version": None,
                "total_count": 0,
                "qc_count": 0
            })
            continue

        latestVersion = versions[0]  # Already sorted by created_at desc
        approvedVersion = None
        qcVersions = [ver for ver in versions if ver.get("is_qc")]

        # Find most recent approved version
        for ver in versions:
            if ver["is_approved"]:
                approvedVersion = ver
                break

        # Determine overall status for this department
        if approvedVersion:
            status = "approved"
            statusDisplay = f"Approved ({approvedVersion['status']})"
        elif latestVersion["is_delivered"]:
            status = "delivered"
            statusDisplay = "Delivered"
        else:
            status = "pending"
            statusDisplay = f"Pending ({latestVersion['status']})"

        hierarchy.append({
            "department": dept,
            "status": status,
            "status_display": statusDisplay,
            "latest_version": latestVersion,
            "approved_version": approvedVersion,
            "total_count": len(versions),
            "qc_count": len(qcVersions)
        })

    return hierarchy


def printApprovalHierarchy(hierarchy, shotCode):
    """
    Print a visual representation of the approval hierarchy.

    Args:
        hierarchy: List from buildApprovalHierarchy
        shotCode: Shot code for display
    """
    print("\n" + "=" * 70)
    print(f"APPROVAL HIERARCHY: {shotCode}")
    print("=" * 70)

    # Status symbols
    symbols = {
        "approved": "✓",
        "delivered": "◐",
        "pending": "○",
        "no_versions": "✗"
    }

    colors = {
        "approved": "\033[92m",  # Green
        "delivered": "\033[93m",  # Yellow
        "pending": "\033[94m",   # Blue
        "no_versions": "\033[91m"  # Red
    }
    reset = "\033[0m"

    # Print pipeline bar
    print("\nPipeline Status:")
    bar = ""
    for item in hierarchy:
        symbol = symbols.get(item["status"], "?")
        color = colors.get(item["status"], "")
        bar += f" {color}[{symbol}]{reset} "
    print(bar)

    # Print department labels
    labels = ""
    for item in hierarchy:
        dept = item["department"][:4]  # Truncate to 4 chars
        labels += f" {dept:^5} "
    print(labels)

    # Print detailed breakdown
    print("\n" + "-" * 80)
    print(f"{'Department':<12} {'Status':<20} {'Latest Version':<35} {'#':<4} {'QC'}")
    print("-" * 80)

    for item in hierarchy:
        dept = item["department"]
        statusDisplay = item["status_display"]
        latestVersion = item["latest_version"]
        count = item["total_count"]
        qcCount = item["qc_count"]

        if latestVersion:
            versionCode = latestVersion["code"]
            if len(versionCode) > 33:
                versionCode = versionCode[:30] + "..."
        else:
            versionCode = "-"

        color = colors.get(item["status"], "")
        print(f"{color}{dept:<12} {statusDisplay:<20} {versionCode:<35} {count:<4} {qcCount}{reset}")

    # Print approval chain summary
    print("\n" + "-" * 80)
    approvedDepts = [item["department"] for item in hierarchy if item["status"] == "approved"]
    pendingDepts = [item["department"] for item in hierarchy if item["status"] == "pending"]
    deliveredDepts = [item["department"] for item in hierarchy if item["status"] == "delivered"]
    missingDepts = [item["department"] for item in hierarchy if item["status"] == "no_versions"]

    if approvedDepts:
        print(f"\033[92mApproved:\033[0m {', '.join(approvedDepts)}")
    if deliveredDepts:
        print(f"\033[93mDelivered:\033[0m {', '.join(deliveredDepts)}")
    if pendingDepts:
        print(f"\033[94mPending:\033[0m {', '.join(pendingDepts)}")
    if missingDepts:
        print(f"\033[91mNo Versions:\033[0m {', '.join(missingDepts)}")

    # Determine overall shot status
    print("\n" + "-" * 80)
    deptsWithVersions = [item for item in hierarchy if item["status"] != "no_versions"]
    if not deptsWithVersions:
        print("\033[91mOverall: NO DATA\033[0m")
    elif all(item["status"] == "approved" for item in deptsWithVersions):
        print("\033[92mOverall: FULLY APPROVED\033[0m")
    elif any(item["status"] == "approved" for item in hierarchy):
        approvedCount = len(approvedDepts)
        totalCount = len(deptsWithVersions)
        print(f"\033[93mOverall: PARTIALLY APPROVED ({approvedCount}/{totalCount})\033[0m")
    else:
        print("\033[91mOverall: NOT APPROVED\033[0m")

    # Quick reference for coordinators
    print("\n" + "-" * 80)
    print("QUICK REFERENCE: \"What versions are in this shot?\"")
    for item in hierarchy:
        dept = item["department"]
        if item["status"] == "approved" and item.get("approved_version"):
            verCode = item["approved_version"]["code"]
            verNum = extractVersionFromCode(verCode)
            print(f"  {dept}: v{verNum}")
        elif item["status"] != "no_versions" and item.get("latest_version"):
            verCode = item["latest_version"]["code"]
            verNum = extractVersionFromCode(verCode)
            print(f"  {dept}: v{verNum} (pending)")
        else:
            print(f"  {dept}: -")


def discoverApprovalHierarchy(sg, shotId, shotCode):
    """
    Run full approval hierarchy discovery for a shot.

    Args:
        sg: ShotGrid connection
        shotId: Shot entity ID
        shotCode: Shot code string

    Returns:
        Dictionary with department versions and hierarchy
    """
    print(f"\n[APPROVAL] Finding department versions for {shotCode}...")
    deptVersions = findDeptVersionsForShot(sg, shotId, shotCode)

    # Count totals
    totalVersions = sum(len(versions) for versions in deptVersions.values())
    deptsWithVersions = sum(1 for versions in deptVersions.values() if versions)
    qcCount = sum(
        sum(1 for ver in versions if ver.get("is_qc"))
        for versions in deptVersions.values()
    )
    print(f"  Found {totalVersions} versions across {deptsWithVersions} departments ({qcCount} QC)")

    print(f"\n[APPROVAL] Building approval hierarchy...")
    hierarchy = buildApprovalHierarchy(deptVersions)

    printApprovalHierarchy(hierarchy, shotCode)

    return {
        "dept_versions": deptVersions,
        "hierarchy": hierarchy
    }


def traceUpstreamCaches(sg, versionId):
    """
    Trace upstream caches from a version to find what department caches it uses.

    Args:
        sg: ShotGrid connection
        versionId: Version entity ID to trace from

    Returns:
        Dictionary with cache chain information
    """
    # Key cache types that represent department handoffs
    cacheTypes = {
        'camera', 'usdLayerStack', 'deformedGeometry', 'animation.atom',
        'render', 'precomp', 'usdSublayer', 'usdPayloadPackage'
    }

    # Get the version's published file
    ver = sg.find_one('Version', [['id', 'is', versionId]],
        ['code', 'tank_published_file', 'sg_status_list'])
    if not ver or not ver.get('tank_published_file'):
        return {'version': ver, 'caches': []}

    startPubId = ver['tank_published_file']['id']

    # Collect all upstream published files recursively
    visited = set()
    caches = []

    def collectUpstream(pubId, depth=0):
        if pubId in visited or depth > 12:
            return
        visited.add(pubId)

        pub = sg.find_one('TankPublishedFile', [['id', 'is', pubId]],
            ['id', 'code', 'tank_type', 'version_number', 'sg_status_list',
             'upstream_tank_published_files', 'created_at', 'created_by'])
        if not pub:
            return

        tankType = (pub.get('tank_type') or {}).get('name', 'N/A')

        # Record if this is a cache type we care about
        if tankType in cacheTypes:
            createdAt = pub.get('created_at')
            caches.append({
                'id': pub['id'],
                'code': pub['code'],
                'type': tankType,
                'version': pub.get('version_number'),
                'status': pub.get('sg_status_list'),
                'depth': depth,
                'user': (pub.get('created_by') or {}).get('name'),
                'createdAt': createdAt.isoformat() if createdAt and hasattr(createdAt, 'isoformat') else str(createdAt) if createdAt else None
            })

        # Recurse into upstream
        for upLink in (pub.get('upstream_tank_published_files') or []):
            collectUpstream(upLink['id'], depth + 1)

    collectUpstream(startPubId)

    return {
        'version': ver,
        'caches': caches
    }


def printCacheChain(cacheData, shotCode):
    """
    Print the cache chain in a readable format.

    Args:
        cacheData: Output from traceUpstreamCaches
        shotCode: Shot code for display
    """
    ver = cacheData.get('version', {})
    caches = cacheData.get('caches', [])

    print("\n" + "=" * 70)
    print(f"CACHE CHAIN: {ver.get('code', 'Unknown')}")
    print("=" * 70)

    if not caches:
        print("No upstream caches found.")
        return

    # Group caches by type
    byType = {}
    for cache in caches:
        cacheType = cache['type']
        if cacheType not in byType:
            byType[cacheType] = []
        byType[cacheType].append(cache)

    # Print in logical order
    typeOrder = ['camera', 'usdLayerStack', 'animation.atom', 'deformedGeometry',
                 'usdSublayer', 'usdPayloadPackage', 'render', 'precomp']

    for cacheType in typeOrder:
        if cacheType in byType:
            typeLabel = cacheType.upper()
            print(f"\n--- {typeLabel} ---")
            # Show unique codes (limit to 5 per type)
            seen = set()
            count = 0
            for cache in byType[cacheType]:
                if cache['code'] not in seen and count < 5:
                    seen.add(cache['code'])
                    verNum = cache.get('version', '?')
                    status = cache.get('status', 'N/A')
                    print(f"  {cache['code']} v{verNum} ({status})")
                    count += 1
            remaining = len(byType[cacheType]) - count
            if remaining > 0:
                print(f"  ... and {remaining} more")

    # Summary
    print("\n" + "-" * 70)
    print(f"Total caches traced: {len(caches)}")
    print(f"Cache types found: {', '.join(sorted(byType.keys()))}")


def discoverFullHierarchy(sg, versionId):
    """
    Discover both dailies and cache chain for a version.

    This provides the 'All' view showing:
    - Department dailies (quicktimes reviewed)
    - Actual caches used in the dependency chain

    Args:
        sg: ShotGrid connection
        versionId: Version entity ID

    Returns:
        Dictionary with dailies hierarchy and cache chain
    """
    # Get version info and its shot
    ver = sg.find_one('Version', [['id', 'is', versionId]],
        ['code', 'entity', 'sg_status_list'])
    if not ver:
        print(f"Version {versionId} not found")
        return None

    shotLink = ver.get('entity')
    if not shotLink or shotLink.get('type') != 'Shot':
        print(f"Version {versionId} is not linked to a Shot")
        return None

    shotId = shotLink['id']
    shot = sg.find_one('Shot', [['id', 'is', shotId]], ['code'])
    shotCode = shot['code']

    print(f"\n{'=' * 70}")
    print(f"FULL HIERARCHY FOR: {ver['code']}")
    print(f"Shot: {shotCode}")
    print(f"{'=' * 70}")

    # Get dailies hierarchy
    print("\n[1/2] Discovering dailies hierarchy...")
    approvalData = discoverApprovalHierarchy(sg, shotId, shotCode)

    # Get cache chain
    print("\n[2/2] Tracing upstream caches...")
    cacheData = traceUpstreamCaches(sg, versionId)
    printCacheChain(cacheData, shotCode)

    return {
        'version': ver,
        'shot_code': shotCode,
        'dailies': approvalData,
        'cache_chain': cacheData
    }


class DailyNode:
    """
    Tree node representing a Version (daily) in the approval chain.

    Attributes:
        id: Version ID
        version: Version entity dictionary
        depth: Depth in the tree
        children: List of child DailyNode objects
        publishedFiles: List of published files for this version
        qcSibling: QC version node that should be positioned alongside this regular node
    """
    __slots__ = ("id", "version", "depth", "children", "publishedFiles", "usedChain", "upstreamInputs", "qcSibling")

    def __init__(self, versionId, version, depth):
        """
        Initialize a DailyNode.

        Args:
            versionId: ShotGrid Version ID
            version: Version entity dictionary
            depth: Depth level in tree
        """
        self.id = versionId
        self.version = version
        self.depth = depth
        self.children = []
        self.publishedFiles = []
        self.usedChain = []
        self.upstreamInputs = []
        self.qcSibling = None


def classifyVersionDepartment(code):
    """
    Classify a version code into department and QC status.

    Args:
        code: Version code string

    Returns:
        Tuple of (department, isQc) or (None, False) if not matched
    """
    codeLower = code.lower()

    # Check QC patterns first (more specific)
    qcPatterns = {
        'Layout': ['qclay'],
        'Anim': ['qcani'],
        'Crowd': ['qccrw'],
        'CFX': ['qccfx'],
        'FX': ['qcfx'],
        'Lighting': ['qclig'],
        'Comp': ['qccomp']
    }

    for dept, patterns in qcPatterns.items():
        for pattern in patterns:
            if pattern in codeLower:
                return (dept, True)

    # Check regular patterns
    regularPatterns = {
        'Plate': ['.ingest.', '.comp.bg', '_rdo_distort_compplate', '_compplate'],
        'Editorial': ['.lineup.'],
        'CMM': ['.cmm.', '_cmm_'],
        'Layout': ['.lay.'],
        'Anim': ['.ani.'],
        'Crowd': ['.crw.'],
        'CFX': ['.cfx.'],
        'FX': ['.fx.'],
        'Lighting': ['.lig.'],
        'ENV': ['.env.'],
        'MP': ['.mp.'],
        'Roto': ['.roto.'],
        'Comp': ['.comp.']
    }

    for dept, patterns in regularPatterns.items():
        for pattern in patterns:
            if pattern in codeLower:
                return (dept, False)

    return (None, False)


def buildDailyChainTree(sg, versionId, maxDepth=10):
    """
    Build a tree of dailies (Versions) showing the approval chain.

    Traces from a Version through its upstream caches to find which
    upstream department dailies it depends on, building a hierarchical
    tree showing the pipeline flow.

    Args:
        sg: ShotGrid connection
        versionId: Starting Version ID
        maxDepth: Maximum depth to traverse

    Returns:
        DailyNode tree root, or None if version not found
    """
    queryStart = time.time()
    
    # Retry logic for SSL errors (reduced to 1 to avoid memory corruption in shotgun_api3)
    startVer = None
    maxRetries = 1
    for attempt in range(maxRetries):
        try:
            startVer = sg.find_one(
                'Version',
                [['id', 'is', versionId]],
                [
                    'entity',
                    'code',
                    'version_number',
                    'description',
                    'sg_status_list',
                    'created_at',
                    'user',
                    'sg_department',
                    'tank_published_file',
                    'sg_path_to_movie',
                    'sg_uploaded_movie',
                    'image',
                    'filmstrip_image',
                    'project',
                ],
            )
            break
        except ssl.SSLError as sslErr:
            if attempt < maxRetries - 1:
                waitTime = 2 ** attempt
                print(f"[SSL ERROR] buildDailyChainTree attempt {attempt + 1}/{maxRetries} failed, retrying in {waitTime}s: {sslErr}")
                time.sleep(waitTime)
            else:
                print(f"[SSL ERROR] buildDailyChainTree all {maxRetries} attempts failed: {sslErr}")
                return None
        except Exception as err:
            print(f"[ERROR] buildDailyChainTree unexpected error: {err}")
            return None
    
    if not startVer:
        return None

    shotLink = startVer.get('entity')
    if not shotLink or shotLink.get('type') != 'Shot':
        return None

    startPublishLink = startVer.get('tank_published_file')
    if not startPublishLink:
        return None

    startPublishId = startPublishLink.get('id')
    if not startPublishId:
        return None

    publishCache = {}

    def getTankTypeName(pub):
        """Return the TankPublishedFile tank type name."""
        if not pub:
            return None
        return (pub.get('tank_type') or {}).get('name')

    def isWorkfilePublish(pub):
        """Return True if publish is considered the authoring workfile pivot."""
        tankTypeName = getTankTypeName(pub) or ''
        return 'workfile' in tankTypeName.lower()

    def iterUpstreamIds(pub):
        """Yield upstream publish IDs from a publish dict."""
        for upstreamLink in (pub.get('upstream_tank_published_files') or []):
            upstreamId = upstreamLink.get('id')
            if upstreamId:
                yield upstreamId

    def findWorkfilePivot(publishId, searchDepth):
        """Find the nearest upstream workfile publish from a starting publish."""
        visitedIds = set()
        queue = [(publishId, 0)]
        while queue:
            currentId, depth = queue.pop(0)
            if currentId in visitedIds or depth > searchDepth:
                continue
            visitedIds.add(currentId)

            pub = sg.find_one(
                'TankPublishedFile',
                [['id', 'is', currentId]],
                ['id', 'tank_type', 'upstream_tank_published_files'],
            )
            if isWorkfilePublish(pub):
                return currentId

            if not pub:
                continue

            for upstreamId in iterUpstreamIds(pub):
                queue.append((upstreamId, depth + 1))

        return None

    workfilePublishId = findWorkfilePivot(startPublishId, maxDepth)
    if not workfilePublishId:
        workfilePublishId = startPublishId

    signalTankTypes = set()
    for tankTypes in HANDOVER_TYPES.values():
        signalTankTypes.update(tankTypes)
    signalTankTypes.update(['usdPayloadPackage', 'usdManifest', 'usdSublayer'])

    usedVersionIds = set([startVer.get('id')])
    visitedPublishIds = set()
    queue = [(startPublishId, 0)]

    batchCount = 0
    
    # Iterative batch fetching: fetch in waves by depth
    while queue:
        # Collect current batch of IDs to fetch
        currentBatch = []
        tempQueue = []
        
        for publishId, depth in queue:
            if publishId in visitedPublishIds or depth > maxDepth:
                continue
            if publishId in publishCache:
                tempQueue.append((publishId, depth))
            else:
                currentBatch.append(publishId)
                tempQueue.append((publishId, depth))
        
        # Break if nothing to process
        if not tempQueue:
            break
        
        # Batch fetch this wave
        if currentBatch:
            batchCount += 1
            fetchStart = time.time()
            pubs = sg.find(
                'TankPublishedFile',
                [['id', 'in', currentBatch]],
                [
                    'id',
                    'code',
                    'tank_type',
                    'version_number',
                    'sg_status_list',
                    'created_at',
                    'created_by',
                    'path',
                    'sg_version',
                    'upstream_tank_published_files',
                ],
                limit=1000,
            )
            for pub in (pubs or []):
                pubId = pub.get('id')
                if pubId:
                    publishCache[pubId] = pub
        
        # Process this wave and collect next wave
        nextQueue = []
        for publishId, depth in tempQueue:
            if publishId in visitedPublishIds:
                continue
            visitedPublishIds.add(publishId)
            
            pub = publishCache.get(publishId)
            if not pub:
                continue
            
            tankTypeName = getTankTypeName(pub)
            tankTypeBase = (tankTypeName or '').split('.', 1)[0]
            if tankTypeBase in signalTankTypes:
                versionLink = pub.get('sg_version')
                if versionLink and versionLink.get('id'):
                    usedVersionIds.add(versionLink.get('id'))
            
            if isWorkfilePublish(pub):
                continue
            
            for upstreamId in iterUpstreamIds(pub):
                nextQueue.append((upstreamId, depth + 1))
        
        queue = nextQueue
    
    queryStart = time.time()
    usedVersions = sg.find(
        'Version',
        [['id', 'in', list(usedVersionIds)]],
        [
            'id',
            'code',
            'description',
            'sg_status_list',
            'created_at',
            'user',
            'entity',
            'sg_department',
            'tank_published_file',
            'sg_path_to_movie',
            'sg_uploaded_movie',
            'image',
            'filmstrip_image',
            'project',
        ],
        limit=500,
    )
    usedVersionMap = {ver.get('id'): ver for ver in (usedVersions or []) if ver.get('id')}
    usedVersionMap[startVer.get('id')] = startVer

    # Always query approved/pushed versions on the same shot to catch departments
    # that might not be linked via upstream_tank_published_files (e.g., CMM, Layout)
    if True:
        fallbackStart = time.time()
        shotId = shotLink.get('id')
        shotEntity = {'type': 'Shot', 'id': shotId}
        fallbackVersions = sg.find(
            'Version',
            [
                ['entity', 'is', shotEntity],
                ['sg_status_list', 'in', ['apr', 'psh', 'dlvr']],
            ],
            [
                'id',
                'code',
                'version_number',
                'description',
                'sg_status_list',
                'created_at',
                'user',
                'entity',
                'sg_department',
                'tank_published_file',
                'sg_path_to_movie',
                'sg_uploaded_movie',
                'image',
                'filmstrip_image',
                'project',
            ],
            limit=500,
        )
        
        fallbackPublishIds = []
        for ver in (fallbackVersions or []):
            verId = ver.get('id')
            if verId and verId not in usedVersionMap:
                usedVersionMap[verId] = ver
                publishLink = ver.get('tank_published_file')
                if publishLink and publishLink.get('id'):
                    fallbackPublishIds.append(publishLink.get('id'))
        
        if fallbackPublishIds:
            fetchStart = time.time()
            fallbackPubs = sg.find(
                'TankPublishedFile',
                [['id', 'in', fallbackPublishIds]],
                [
                    'id',
                    'code',
                    'tank_type',
                    'upstream_tank_published_files',
                    'path',
                ],
                limit=500,
            )
            for pub in (fallbackPubs or []):
                pubId = pub.get('id')
                if pubId:
                    publishCache[pubId] = pub

    def classifyVersion(ver):
        """Classify a Version into (department, isQc) using sg_department first."""
        code = ver.get('code') or ''
        deptFromCode, isQc = classifyVersionDepartment(code)

        dept = ver.get('sg_department')
        if not dept:
            dept = deptFromCode
        if dept and dept not in DEPARTMENTS and deptFromCode:
            dept = deptFromCode

        return dept, isQc

    startDept, startIsQc = classifyVersion(startVer)
    pipelineOrder = list(reversed(DEPARTMENTS))
    startIndex = 0
    if startDept in pipelineOrder:
        startIndex = pipelineOrder.index(startDept)
    orderedDepts = pipelineOrder[startIndex:]

    usedByDept = {dept: [] for dept in DEPARTMENTS}
    for ver in usedVersionMap.values():
        dept, _ = classifyVersion(ver)
        if dept in usedByDept:
            usedByDept[dept].append(ver)

    for dept in usedByDept:
        usedByDept[dept].sort(
            key=lambda item: item.get('created_at') or '',
            reverse=True,
        )

    def getVariantKey(versionData, deptName, isQc):
        """Return a stable key for grouping multiple versions within one department."""
        versionCode = (versionData.get('code') or '').lower()
        cleanedCode = re.sub(r'[._]v\d+(?:[._].*)?$', '', versionCode)
        if isQc:
            marker = f"qc{deptName.lower()}"
            if marker in cleanedCode:
                return marker
            return f"qc_{deptName.lower()}"

        marker = f".{deptName.lower()}."
        if marker in cleanedCode:
            return cleanedCode.split(marker, 1)[0]
        return cleanedCode

    def findDailyForQc(qcVer, regularVersions):
        """
        Find which daily version created a QC by tracing upstream publishes.
        Returns the daily version that the QC was created from.
        """
        qcPublishLink = qcVer.get('tank_published_file')
        if not qcPublishLink or not qcPublishLink.get('id'):
            return None
        
        qcPublish = publishCache.get(qcPublishLink.get('id'))
        if not qcPublish:
            return None
        
        upstreamLinks = qcPublish.get('upstream_tank_published_files') or []
        upstreamPublishIds = {link.get('id') for link in upstreamLinks if link.get('id')}
        
        for regularVer in regularVersions:
            regularPublishLink = regularVer.get('tank_published_file')
            if regularPublishLink and regularPublishLink.get('id'):
                if regularPublishLink.get('id') in upstreamPublishIds:
                    return regularVer
        
        return None
    
    def queryUsdVariantsForDepartment(deptName, shotEntity):
        """
        Query USD publishes (usdPayloadPackage, usdSublayer) for FX/CFX departments.
        Returns list of Version entities (real or pseudo) for USD publishes.
        
        For USD publishes WITH sg_version links: returns the actual Version entity.
        For USD publishes WITHOUT sg_version links: creates pseudo-Version entry for display.
        """
        if deptName not in ['FX', 'CFX']:
            return []
        
        if not shotEntity or not shotEntity.get('id'):
            return []
        
        try:
            queryStart = time.time()
            usdPublishes = sg.find(
                'TankPublishedFile',
                [
                    ['entity', 'is', shotEntity],
                    {
                        'filter_operator': 'any',
                        'filters': [
                            ['tank_type.TankType.code', 'is', 'usdPayloadPackage'],
                            ['tank_type.TankType.code', 'is', 'usdSublayer'],
                        ]
                    }
                ],
                [
                    'id',
                    'code',
                    'name',
                    'sg_version',
                    'tank_type',
                    'path',
                    'version_number',
                    'created_at',
                    'created_by',
                ],
                limit=500,
            )
            queryTime = time.time() - queryStart
            
            usdVersions = []
            realVersionCount = 0
            pseudoVersionCount = 0
            
            variantGroups = {}
            
            for pub in (usdPublishes or []):
                pubCode = pub.get('code') or pub.get('name') or ''
                pubPath = pub.get('path', {}).get('local_path') or ''
                
                deptMarker = f".{deptName.lower()}."
                if deptMarker in pubCode.lower() or deptMarker in pubPath.lower():
                    versionLink = pub.get('sg_version')
                    
                    if versionLink and versionLink.get('id'):
                        versionId = versionLink.get('id')
                        if versionId not in usedVersionMap:
                            fullVersion = sg.find_one(
                                'Version',
                                [['id', 'is', versionId]],
                                [
                                    'id',
                                    'code',
                                    'description',
                                    'sg_status_list',
                                    'created_at',
                                    'user',
                                    'entity',
                                    'sg_department',
                                    'version_number',
                                    'tank_published_file',
                                    'sg_path_to_movie',
                                ],
                            )
                            if fullVersion:
                                dept, isQc = classifyVersion(fullVersion)
                                if not isQc and dept == deptName:
                                    usdVersions.append(fullVersion)
                                    usedVersionMap[versionId] = fullVersion
                                    publishCache[pub.get('id')] = pub
                                    realVersionCount += 1
                        else:
                            existingVer = usedVersionMap[versionId]
                            dept, isQc = classifyVersion(existingVer)
                            if not isQc and dept == deptName:
                                usdVersions.append(existingVer)
                                realVersionCount += 1
                    else:
                        variantName = pubCode.rsplit('_v', 1)[0] if '_v' in pubCode else pubCode
                        versionNum = pub.get('version_number', 0)
                        
                        if variantName not in variantGroups:
                            variantGroups[variantName] = []
                        variantGroups[variantName].append((versionNum, pub))
            
            for variantName, versions in variantGroups.items():
                versions.sort(key=lambda x: x[0], reverse=True)
                latestVersionNum, latestPub = versions[0]
                
                pubCode = latestPub.get('code') or latestPub.get('name') or ''
                pseudoId = f"usd_pub_{latestPub.get('id')}"
                
                if pseudoId not in usedVersionMap:
                    pseudoVersion = {
                        'id': pseudoId,
                        'code': pubCode,
                        'description': f"USD Publish (no Version link)",
                        'sg_status_list': 'usd_publish',
                        'created_at': latestPub.get('created_at'),
                        'user': latestPub.get('created_by'),
                        'entity': shotEntity,
                        'sg_department': deptName,
                        'version_number': latestVersionNum,
                        'tank_published_file': {'id': latestPub.get('id'), 'type': 'TankPublishedFile'},
                        'sg_path_to_movie': None,
                        '_is_usd_pseudo': True,
                    }
                    usdVersions.append(pseudoVersion)
                    usedVersionMap[pseudoId] = pseudoVersion
                    publishCache[latestPub.get('id')] = latestPub
                    pseudoVersionCount += 1
            
            return usdVersions
        except Exception as ex:
            import traceback
            traceback.print_exc()
            return []
    
    def pickRegularVersions(deptName, deptVersions, qcVer=None):
        """
        Pick regular versions for a department.
        
        For Layout/Anim: Only pick the daily that created the QC render (trace upstream).
        For FX/CFX: Pick latest per variant (blended QC, data passes through).
                    Also query USD variants (usdPayloadPackage, usdSublayer).
        For others: Pick latest.
        """
        qcRequiredDepts = {'Layout', 'Anim'}
        blendedQcDepts = {'FX', 'CFX'}
        
        regularVersions = [ver for ver in deptVersions if not classifyVersion(ver)[1]]
        if not regularVersions:
            return []
        
        if deptName in qcRequiredDepts and qcVer:
            dailyForQc = findDailyForQc(qcVer, regularVersions)
            if dailyForQc:
                return [dailyForQc]
            return [regularVersions[0]]
        
        if deptName in blendedQcDepts:
            usdVariants = queryUsdVariantsForDepartment(deptName, shotLink)
            allVersions = regularVersions + usdVariants
            
            chosenByKey = {}
            for versionData in allVersions:
                variantKey = getVariantKey(versionData, deptName, False)
                if variantKey not in chosenByKey:
                    chosenByKey[variantKey] = versionData
            chosenVersions = list(chosenByKey.values())
            chosenVersions.sort(
                key=lambda item: item.get('created_at') or '',
                reverse=True,
            )
            return chosenVersions
        
        return [regularVersions[0]]

    def buildUpstreamInputs(linkedPublish):
        """Build upstream inputs list from a linked publish."""
        if not linkedPublish:
            return []
        upstreamLinks = linkedPublish.get('upstream_tank_published_files') or []
        upstreamInputs = []
        for upLink in upstreamLinks:
            upId = upLink.get('id')
            if upId and upId in publishCache:
                upPub = publishCache[upId]
                tankType = (upPub.get('tank_type') or {}).get('name') or 'unknown'
                if tankType not in ['workfile', 'workfileChunk']:
                    upstreamInputs.append(upPub)
        return upstreamInputs

    def buildNodeForVersion(versionData, nodeDepth):
        """Create a DailyNode for a Version and populate publishedFiles + upstreamInputs."""
        versionNode = DailyNode(versionData.get('id'), versionData, nodeDepth)
        publishLink = versionData.get('tank_published_file')
        if publishLink and publishLink.get('id'):
            linkedPublish = publishCache.get(publishLink.get('id'))
            versionNode.publishedFiles = [linkedPublish] if linkedPublish else []
            versionNode.upstreamInputs = buildUpstreamInputs(linkedPublish)
        return versionNode

    # Build department groups: each group contains one QC + multiple regular versions
    deptGroups = []
    usedChainIds = set([startVer.get('id')])
    for deptName in orderedDepts[1:]:
        deptVersions = usedByDept.get(deptName, [])
        if not deptVersions:
            continue

        qcVersions = [ver for ver in deptVersions if classifyVersion(ver)[1]]
        qcVer = qcVersions[0] if qcVersions else None
        regularVersions = pickRegularVersions(deptName, deptVersions, qcVer)

        if qcVer:
            qcId = qcVer.get('id')
            if qcId and qcId not in usedChainIds:
                usedChainIds.add(qcId)

        for regularVer in regularVersions:
            verId = regularVer.get('id')
            if verId and verId not in usedChainIds:
                usedChainIds.add(verId)

        if qcVer or regularVersions:
            deptGroups.append({
                'deptName': deptName,
                'qcVer': qcVer,
                'regularVersions': regularVersions,
            })

    # Build tree: keep discovery order but allow multiple children per parent
    # Departments discovered at same level become siblings (children of same parent)
    rootNode = DailyNode(startVer.get('id'), startVer, 0)
    parentNodes = [rootNode]
    depth = 1

    for deptGroup in deptGroups:
        qcVer = deptGroup.get('qcVer')
        regularVersions = deptGroup.get('regularVersions') or []

        qcNodeTemplate = None
        if qcVer:
            qcNodeTemplate = buildNodeForVersion(qcVer, depth)

        if regularVersions:
            regularNodes = []
            for regularVer in regularVersions:
                regularNode = buildNodeForVersion(regularVer, depth)
                if qcNodeTemplate:
                    regularNode.qcSibling = qcNodeTemplate
                regularNodes.append(regularNode)

            # Add all regular nodes as children to ALL current parents
            for parentNode in parentNodes:
                parentNode.children.extend(regularNodes)
            
            # Move to next depth level with these nodes as new parents
            parentNodes = list(regularNodes)
            depth += 1
            continue

        if qcNodeTemplate:
            for parentNode in parentNodes:
                parentNode.children.append(qcNodeTemplate)
            parentNodes = [qcNodeTemplate]
            depth += 1

    rootPublish = publishCache.get(startPublishId)
    rootNode.publishedFiles = [rootPublish] if rootPublish else []
     
    if rootPublish:
        upstreamLinks = rootPublish.get('upstream_tank_published_files') or []
        upstreamInputs = []
        for upLink in upstreamLinks:
            upId = upLink.get('id')
            if upId and upId in publishCache:
                upPub = publishCache[upId]
                tankType = (upPub.get('tank_type') or {}).get('name') or 'unknown'
                if tankType not in ['workfile', 'workfileChunk']:
                    upstreamInputs.append(upPub)
        rootNode.upstreamInputs = upstreamInputs

    # Rebuild usedChainVersions list with depth tracking for summary generation
    usedChainVersions = [(startVer, 0)]
    currentDepth = 1
    for deptGroup in deptGroups:
        qcVer = deptGroup.get('qcVer')
        regularVersions = deptGroup.get('regularVersions') or []
        if qcVer:
            usedChainVersions.append((qcVer, currentDepth))
        for regularVer in regularVersions:
            usedChainVersions.append((regularVer, currentDepth))
        if qcVer or regularVersions:
            currentDepth += 1

    usedChain = []
    usedDeptCounts = defaultdict(int)
    for ver, depth in usedChainVersions:
        dept, isQc = classifyVersion(ver)
        verId = ver.get('id')
        if dept:
            usedDeptCounts[dept] += 1

        createdAt = ver.get('created_at')
        createdAtStr = None
        if createdAt:
            createdAtStr = createdAt.isoformat() if hasattr(createdAt, 'isoformat') else str(createdAt)

        publishId = (ver.get('tank_published_file') or {}).get('id')
        layerStack = []
        if publishId and publishId in publishCache:
            linkedPub = publishCache[publishId]
            upstreamPubs = linkedPub.get('upstream_tank_published_files') or []
            for upPub in upstreamPubs:
                upId = upPub.get('id')
                if upId and upId in publishCache:
                    upData = publishCache[upId]
                    tankType = (upData.get('tank_type') or {}).get('name') or 'unknown'
                    if tankType not in ['workfile', 'workfileChunk']:
                        layerStack.append({
                            'id': upId,
                            'code': upData.get('code'),
                            'type': tankType,
                            'path': upData.get('path', {}).get('local_path') if isinstance(upData.get('path'), dict) else upData.get('path')
                        })

        usedChain.append({
            'department': dept,
            'isQc': isQc,
            'versionId': verId,
            'versionCode': ver.get('code'),
            'versionNumber': extractVersionFromCode(ver.get('code') or ''),
            'sgStatus': ver.get('sg_status_list'),
            'user': (ver.get('user') or {}).get('name'),
            'createdAt': createdAtStr,
            'publishId': publishId,
            'description': ver.get('description'),
            'path': ver.get('sg_path_to_movie'),
            'streamingUrl': ver.get('sg_uploaded_movie'),
            'thumbnailUrl': ver.get('image'),
            'entity': ver.get('entity'),
            'layerStack': layerStack,
            'depth': depth,
        })

    for item in usedChain:
        dept = item.get('department')
        if dept:
            item['totalCount'] = usedDeptCounts.get(dept, 0)

    rootNode.usedChain = usedChain

    return rootNode


def dailyNodeToDict(node):
    """
    Convert DailyNode to dictionary for JSON serialization.

    Produces a format compatible with the existing visualization system.

    Args:
        node: DailyNode object

    Returns:
        Dictionary representation of the daily tree
    """
    if node is None:
        return None

    ver = node.version
    code = ver.get('code', '')

    # Classify department
    dept = ver.get('sg_department')
    deptFromCode, isQc = classifyVersionDepartment(code)
    if not dept:
        dept = deptFromCode
    deptLabel = f"{dept}QC" if isQc else dept
    if not dept:
        deptLabel = "Unknown"

    # Extract version number from code
    verNum = extractVersionFromCode(code)

    # Format dates
    createdAt = ver.get('created_at')
    dateStr = None
    timeStr = None
    if createdAt:
        try:
            if hasattr(createdAt, 'strftime'):
                dateStr = createdAt.strftime('%Y-%m-%d')
                timeStr = createdAt.strftime('%H:%M:%S')
            else:
                dateStr = str(createdAt)
        except Exception:
            dateStr = str(createdAt)

    # Get user name
    user = ver.get('user')
    userName = user.get('name') if user else None

    # Get entity info
    entity = ver.get('entity')
    project = ver.get('project')

    # Get path to movie (QuickTime)
    pathToMovie = ver.get('sg_path_to_movie')

    # Get thumbnail image URL
    thumbnailUrl = ver.get('image')

    # Build ShotGrid URLs
    versionUrl = buildShotgridUrl('Version', node.id)
    publishUrl = None
    entityUrl = None
    projectUrl = None
    mediaCenterUrl = None

    # Build publish URL from tank_published_file if available
    tankPublishedFile = ver.get('tank_published_file')
    if tankPublishedFile and isinstance(tankPublishedFile, dict):
        publishId = tankPublishedFile.get('id')
        if publishId:
            publishUrl = buildShotgridUrl('TankPublishedFile', publishId)

    if entity and isinstance(entity, dict):
        entityUrl = buildShotgridUrl(entity.get('type'), entity.get('id'))

    projectId = None
    if project and isinstance(project, dict):
        projectId = project.get('id')
        projectUrl = buildShotgridUrl('Project', projectId)

    # Build media center URL if we have both project and version IDs
    if projectId and node.id:
        mediaCenterUrl = buildMediaCenterUrl(projectId, node.id)

    # Build simplified name for display
    # Remove shot code prefix for cleaner display
    displayName = code
    if entity and entity.get('name'):
        shotCode = entity.get('name')
        if code.startswith(shotCode + '.'):
            displayName = code[len(shotCode) + 1:]

    # Format upstream inputs (layerStack)
    pubFiles = []
    for pub in node.upstreamInputs:
        tankType = (pub.get('tank_type') or {}).get('name', 'unknown')
        pubCreatedAt = pub.get('created_at')
        pubDateStr = None
        if pubCreatedAt:
            try:
                if hasattr(pubCreatedAt, 'strftime'):
                    pubDateStr = pubCreatedAt.strftime('%Y-%m-%d %H:%M')
                else:
                    pubDateStr = str(pubCreatedAt)
            except Exception:
                pubDateStr = str(pubCreatedAt)

        pubUser = pub.get('created_by')
        pubUserName = pubUser.get('name') if pubUser else None

        pubFiles.append({
            'id': pub.get('id'),
            'code': pub.get('code'),
            'type': tankType,
            'version': pub.get('version_number'),
            'status': pub.get('sg_status_list'),
            'user': pubUserName,
            'date': pubDateStr,
            'path': pub.get('path', {}).get('local_path') if isinstance(pub.get('path'), dict) else pub.get('path')
        })

    result = {
        'publishId': node.id,  # Use version ID as publishId for compatibility
        'pub': {
            'id': node.id,
            'name': displayName,
            'code': code,
            'tank_type': {
                'name': deptLabel  # Use department as "type" for visualization
            },
            'version_number': verNum,
            'created_at': createdAt,
            'created_date': dateStr,
            'created_time': timeStr,
            'created_by': user,
            'sg_status_list': ver.get('sg_status_list'),
            'department': dept,
            'is_qc': isQc,
            'entity': entity,
            'project': project,
            'path_to_movie': pathToMovie,
            'thumbnail_url': thumbnailUrl,
            'sg_links': {
                'publish': publishUrl,
                'version': versionUrl,
                'entity': entityUrl,
                'project': projectUrl,
                'media_center': mediaCenterUrl
            },
            'published_files': pubFiles
        },
        'depth': node.depth,
        'children': []
    }

    if node.children:
        result['children'] = [
            dailyNodeToDict(child)
            for child in node.children
            if child is not None
        ]
    
    # Add QC sibling if present
    if node.qcSibling:
        result['qcSibling'] = dailyNodeToDict(node.qcSibling)

    return result


def saveResults(results, filename):
    """
    Save results to JSON file.

    Args:
        results: Discovery results dictionary
        filename: Output filename
    """
    def serializeDate(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    with open(filename, "w") as outFile:
        json.dump(results, outFile, indent=2, default=serializeDate)
    print(f"\nResults saved to: {filename}")


def main():
    """
    Main entry point.
    """
    parser = argparse.ArgumentParser(
        description="Discover ShotGrid data structure for Approval Hierarchy"
    )
    parser.add_argument("--shot-id", type=str, help="Shot entity ID")
    parser.add_argument("--shot-code", type=str, help="Shot code (e.g., 13ta_1280)")
    parser.add_argument("--version-code", type=str,
        help="Version code (e.g., 312ljn_2380.lig.creative.main.defPart.v6)")
    parser.add_argument("--version-id", type=str, help="Version entity ID to trace")
    parser.add_argument("--full", action="store_true",
        help="Show full hierarchy (dailies + cache chain) for a version")
    parser.add_argument("--output", type=str, help="Output JSON file path")

    args = parser.parse_args()

    shotId = normalizeNumericId(args.shot_id)
    versionId = normalizeNumericId(args.version_id)

    if args.shot_id and shotId is None:
        print(f"ERROR: Invalid shot ID '{args.shot_id}'")
        sys.exit(1)

    if args.version_id and versionId is None:
        print(f"ERROR: Invalid version ID '{args.version_id}'")
        sys.exit(1)

    if not any([shotId, args.shot_code, args.version_code, versionId]):
        parser.print_help()
        print("\nERROR: Provide --shot-id, --shot-code, --version-code, or --version-id")
        sys.exit(1)

    print("Connecting to ShotGrid...")
    sg = getShotgridConnection()
    print("Connected!")

    results = None

    # Full hierarchy mode: show dailies + cache chain for a version
    if versionId and args.full:
        results = discoverFullHierarchy(sg, versionId)
        if results:
            outputFile = args.output or f"full_hierarchy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            saveResults(results, outputFile)
        sys.exit(0)

    if versionId:
        results = discoverFromVersion(sg, versionId)
    elif shotId:
        results = discoverFromShot(sg, shotId)
    elif args.version_code:
        shotCode = extractShotCodeFromVersionCode(args.version_code)
        print(f"Extracted shot code: {shotCode}")
        shotId = findShotByCode(sg, shotCode)
        if shotId:
            results = discoverFromShot(sg, shotId)
        else:
            print(f"ERROR: Could not find shot with code '{shotCode}'")
            sys.exit(1)
    elif args.shot_code:
        shotId = findShotByCode(sg, args.shot_code)
        if shotId:
            results = discoverFromShot(sg, shotId)
        else:
            print(f"ERROR: Could not find shot with code '{args.shot_code}'")
            sys.exit(1)

    if results:
        printSummary(results)

        # Run approval hierarchy for shot-based discovery
        if results.get("shot_info") and not results.get("approval_hierarchy"):
            shotCode = results["shot_info"].get("code")
            shotId = results.get("shot_id") or results["shot_info"].get("id")
            if shotCode and shotId:
                approvalResults = discoverApprovalHierarchy(sg, shotId, shotCode)
                results["approval_hierarchy"] = approvalResults

        outputFile = args.output or f"discovery_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        saveResults(results, outputFile)


if __name__ == "__main__":
    main()
