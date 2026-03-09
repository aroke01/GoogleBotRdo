#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Approval Hierarchy Logic.

Purpose:
    Reconstruct the chain of approvals across departments that led to a Version.
    Answer: "Which approvals led to this?"
    Audience: Production, Coordinators, Leads.

Usage:
    from approval_hierarchy import getApprovalChain
    chain = getApprovalChain(sgConnection, versionId)
"""

from collections import defaultdict


# =============================================================================
# CONSTANTS - Based on Discovery (Shot: 306dtt_1380, 2025-12-08)
# =============================================================================

# Pipeline order (downstream to upstream)
# We walk backwards through this to find inputs
PIPELINE_ORDER = ['Comp', 'Lighting', 'FX', 'CFX', 'Crowd', 'Anim', 'Layout']

# Department values as they appear in sg_department field (capitalized)
DEPARTMENTS = {
    'Layout', 'Anim', 'Crowd', 'CFX', 'FX', 'Lighting', 'Comp',
    'Reference', 'VFXOffline'
}

# Status codes that indicate "approved/official"
STATUS_APPROVED = {'apr', 'psh'}

# Status codes that indicate delivered
STATUS_DELIVERED = {'dlvr'}

# All "good" statuses for chain health
STATUS_GOOD = STATUS_APPROVED | STATUS_DELIVERED

# Tank types that represent handover artifacts between departments
# These are the caches/outputs that flow from one dept to the next
HANDOVER_TYPES = {
    'Layout': {'camera', 'usdLayerStack', 'usdManifest'},
    'Anim': {'deformedGeometry', 'animation.atom'},
    'Crowd': {'deformedGeometry'},
    'CFX': {'deformedGeometry'},
    'FX': {'render'},
    'Lighting': {'render'},
    'Comp': {'precomp', 'render', 'movie'}
}

# QC Version naming pattern: {shot}.qc{dept}.primary.main.defPart.v{N}
# Maps department to the code fragment in version names
DEPT_CODE_MAP = {
    'Layout': 'qclay',
    'Anim': 'qcani',
    'Crowd': 'qccrowd',
    'CFX': 'qccfx',
    'FX': 'qcfx',
    'Lighting': 'qclit',
    'Comp': 'qccomp'
}

# Fields to fetch for Versions
VERSION_FIELDS = [
    'code', 'sg_department', 'sg_status_list', 'created_at', 'user',
    'entity', 'project', 'tank_published_file', 'sg_path_to_movie'
]

# Fields to fetch for TankPublishedFiles
PUB_FIELDS = [
    'code', 'name', 'tank_type', 'sg_status_list', 'created_at', 'created_by',
    'upstream_tank_published_files', 'downstream_tank_published_files',
    'version_number', 'entity', 'sg_version'
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def getDepartmentFromVersion(version):
    """
    Extract department from a Version entity.

    Args:
        version: ShotGrid Version entity dict

    Returns:
        Department string or None
    """
    return version.get('sg_department')


def getDepartmentFromCode(code):
    """
    Try to extract department from a Version code using naming convention.

    Args:
        code: Version code string (e.g., "306dtt_1380.qcani.primary.main.defPart.v2")

    Returns:
        Department string or None
    """
    if not code:
        return None

    codeLower = code.lower()
    for dept, fragment in DEPT_CODE_MAP.items():
        if fragment in codeLower:
            return dept

    return None


def isApproved(entity):
    """
    Check if an entity (Version or Pub) has an approved status.

    Args:
        entity: ShotGrid entity dict with sg_status_list field

    Returns:
        Boolean
    """
    status = entity.get('sg_status_list')
    return status in STATUS_APPROVED


def getShotFromVersion(sg, versionId):
    """
    Get the Shot entity linked to a Version.

    Args:
        sg: ShotGrid connection
        versionId: Version entity ID

    Returns:
        Shot entity dict or None
    """
    version = sg.find_one(
        'Version',
        [['id', 'is', versionId]],
        ['entity', 'code', 'sg_department', 'sg_status_list']
    )

    if not version:
        return None

    entity = version.get('entity')
    if entity and entity.get('type') == 'Shot':
        return entity

    return None


# =============================================================================
# CORE LOGIC
# =============================================================================

def getApprovedVersionsPerDepartment(sg, shotId):
    """
    Find the latest approved Version for each department on a Shot.

    This represents the "Official" chain - what production expects.

    Args:
        sg: ShotGrid connection
        shotId: Shot entity ID

    Returns:
        Dict mapping department -> latest approved Version (or None)
    """
    result = {}

    for dept in PIPELINE_ORDER:
        versions = sg.find(
            'Version',
            [
                ['entity', 'is', {'type': 'Shot', 'id': shotId}],
                ['sg_department', 'is', dept],
                ['sg_status_list', 'in', list(STATUS_APPROVED)]
            ],
            VERSION_FIELDS,
            order=[{'field_name': 'created_at', 'direction': 'desc'}],
            limit=1
        )

        result[dept] = versions[0] if versions else None

    return result


def traceActualChain(sg, versionId, maxDepth=10):
    """
    Trace the actual dependency chain from a Version.

    Walks upstream through TankPublishedFiles to find what was actually used.

    Args:
        sg: ShotGrid connection
        versionId: Starting Version ID
        maxDepth: Maximum depth to trace

    Returns:
        List of stages with actual dependencies used
    """
    # Get the starting version
    version = sg.find_one('Version', [['id', 'is', versionId]], VERSION_FIELDS)
    if not version:
        return []

    chain = []
    visited = set()

    # Get linked published files
    linkedPubs = version.get('tank_published_file') or []
    if not linkedPubs:
        return [{
            'department': getDepartmentFromVersion(version) or getDepartmentFromCode(version.get('code')),
            'version': version,
            'pubs': [],
            'upstreamDepts': []
        }]

    pubIds = [p['id'] for p in linkedPubs]
    toProcess = pubIds
    depth = 0

    # Group pubs by department as we trace
    deptPubs = defaultdict(list)

    while toProcess and depth < maxDepth:
        depth += 1

        pubs = sg.find(
            'TankPublishedFile',
            [['id', 'in', toProcess]],
            PUB_FIELDS
        )

        nextBatch = []
        for pub in pubs:
            if pub['id'] in visited:
                continue
            visited.add(pub['id'])

            # Try to determine department from linked version or naming
            sgVersion = pub.get('sg_version')
            dept = None
            if sgVersion:
                # Fetch version to get department
                versionData = sg.find_one(
                    'Version',
                    [['id', 'is', sgVersion['id']]],
                    ['sg_department', 'code']
                )
                if versionData:
                    dept = versionData.get('sg_department') or getDepartmentFromCode(versionData.get('code'))

            if dept:
                deptPubs[dept].append(pub)

            # Queue upstream for next iteration
            upstream = pub.get('upstream_tank_published_files') or []
            for upPub in upstream:
                upId = upPub.get('id')
                if upId and upId not in visited:
                    nextBatch.append(upId)

        toProcess = list(set(nextBatch))

    # Build chain from collected data
    startDept = getDepartmentFromVersion(version) or getDepartmentFromCode(version.get('code'))

    chain.append({
        'department': startDept,
        'role': 'current',
        'version': version,
        'status': version.get('sg_status_list'),
        'isApproved': isApproved(version)
    })

    # Add upstream departments in pipeline order
    for dept in PIPELINE_ORDER:
        if dept == startDept:
            continue
        if dept in deptPubs:
            chain.append({
                'department': dept,
                'role': 'upstream',
                'pubs': deptPubs[dept],
                'pubCount': len(deptPubs[dept])
            })

    return chain


def getApprovalChain(sg, versionId):
    """
    Main entry point for Approval Hierarchy.

    Builds both the "Actual" chain (what was used) and "Official" chain
    (what's approved), then compares them.

    Args:
        sg: ShotGrid connection
        versionId: Starting Version ID

    Returns:
        Dict with:
        - version: Starting version info
        - shot: Shot entity
        - actualChain: What was actually used
        - officialChain: Latest approved per dept
        - stages: Merged analysis with health status
    """
    # Get shot from version
    shot = getShotFromVersion(sg, versionId)
    if not shot:
        return {'error': 'Could not find Shot for this Version'}

    shotId = shot['id']

    # Get both chains
    actualChain = traceActualChain(sg, versionId)
    officialChain = getApprovedVersionsPerDepartment(sg, shotId)

    # Merge and analyze
    stages = []
    for stage in actualChain:
        dept = stage.get('department')
        if not dept:
            continue

        official = officialChain.get(dept)

        stageData = {
            'department': dept,
            'role': stage.get('role', 'upstream'),
            'actual': stage,
            'official': {
                'code': official.get('code') if official else None,
                'status': official.get('sg_status_list') if official else None,
                'exists': official is not None
            } if dept in PIPELINE_ORDER else None,
            'health': 'unknown'
        }

        # Determine health
        if stage.get('role') == 'current':
            stageData['health'] = 'current'
        elif official is None:
            stageData['health'] = 'no_approved'
        elif stage.get('isApproved'):
            stageData['health'] = 'good'
        else:
            stageData['health'] = 'pending'

        stages.append(stageData)

    return {
        'versionId': versionId,
        'shot': shot,
        'stages': stages,
        'officialChain': {
            dept: {
                'code': ver.get('code') if ver else None,
                'status': ver.get('sg_status_list') if ver else None
            }
            for dept, ver in officialChain.items()
        }
    }
