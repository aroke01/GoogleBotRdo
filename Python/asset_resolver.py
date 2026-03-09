"""
Asset Publish Resolver - Single Source of Truth

Fault-tolerant resolver for asset department state across the pipeline.
Powers Asset Analysis tables, department publish state, and audit systems.

Key guarantees:
- NEVER returns None/empty/unknown
- Always deterministic output
- Handles duplicates, missing data, schema drift
- Classification cascade: step > tank_type > pattern > unclassified
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any


DEPARTMENTS = ['model', 'texture', 'shading', 'rig', 'groom']


STEP_TO_DEPT = {
    'Modeling': 'model',
    'Texturing': 'texture',
    'Shading': 'shading',
    'Rigging': 'rig',
    'Hair': 'groom',
    'Grooming': 'groom'
}


TANK_TYPE_TO_DEPT = {
    'geometry': 'model',
    'model': 'model',
    'texture': 'texture',
    'textureBundle': 'texture',
    'textureBundle2': 'texture',
    'lightTexture': 'texture',
    'shading': 'shading',
    'lookdev': 'shading',
    'rig': 'rig',
    'groom': 'groom',
    'yeti': 'groom'
}


PATTERN_TO_DEPT = {
    'model': [r'\.mod\.', r'\.hi\.', r'\.mi\.', r'\.proxy\.'],
    'texture': [r'\.tex\.', r'texture'],
    'shading': [r'\.shd\.', r'^shd\.', r'shading', r'lookdev'],
    'rig': [r'\.rig\.', r'^rig\.'],
    'groom': [r'\.hair\.', r'\.groom\.', r'groom', r'yeti']
}


NOISE_PATTERNS = [
    'deformed', '.cache', 'workfile', 'workfilechunk',
    'camera', 'render', 'precomp', 'movie', 'turntable',
    'autoreview', 'assetreview', 'mocaprig', 'texturecard'
]


def fetchCandidates(sg, assetId):
    """Fetch all publish candidates for an asset.
    
    Args:
        sg: ShotGrid connection.
        assetId: Asset entity ID.
        
    Returns:
        List of publish dictionaries.
    """
    filters = [
        ['entity.Asset.id', 'is', assetId],
        ['sg_status_list', 'not_in', ['void', 'del', 'bid', 'omt', 'hld']]
    ]
    
    fields = [
        'id',
        'code',
        'name',
        'version_number',
        'created_at',
        'created_by',
        'sg_status_list',
        'tank_type',
        'task',
        'task.Task.step'
    ]
    
    try:
        publishes = sg.find('TankPublishedFile', filters, fields)
        return publishes
    except Exception as error:
        print(f"[ERROR] ShotGrid query failed in fetchCandidates: {error}")
        print(f"[ERROR] Returning empty list to allow analyzer to continue")
        return []


def normalizeVersion(publish):
    """Normalize version_number to integer.
    
    Priority:
    1. version_number field
    2. Parse from code/name (v001, v12, version12)
    3. Fallback = 0
    
    Args:
        publish: Publish dictionary.
        
    Returns:
        Integer version number (never None).
    """
    versionNumber = publish.get('version_number')
    if versionNumber is not None:
        try:
            return int(versionNumber)
        except (ValueError, TypeError):
            pass
    
    code = publish.get('code') or publish.get('name') or ''
    match = re.search(r'[._]v(\d+)(?:[._]|$)', code, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    match = re.search(r'version[._]?(\d+)', code, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    return 0


def parseDateTime(value):
    """Parse datetime to datetime object.
    
    Args:
        value: Datetime string or datetime object.
        
    Returns:
        datetime object or datetime.min.
    """
    if not value:
        return datetime.min
    
    if isinstance(value, datetime):
        return value
    
    try:
        from dateutil import parser
        return parser.parse(value)
    except (ImportError, ValueError, TypeError):
        pass
    
    try:
        cleanValue = str(value).replace('Z', '+00:00')
        return datetime.fromisoformat(cleanValue)
    except (ValueError, TypeError):
        return datetime.min


def isNoisePublish(publish):
    """Check if publish is noise (cache, workfile, etc).
    
    Args:
        publish: Publish dictionary.
        
    Returns:
        True if noise, False otherwise.
    """
    tankType = ((publish.get('tank_type') or {}).get('name') or '').lower()
    code = (publish.get('code') or '').lower()
    name = (publish.get('name') or '').lower()
    
    for pattern in NOISE_PATTERNS:
        if pattern in tankType or pattern in code or pattern in name:
            return True
    
    return False


def classifyPublishByStep(publish):
    """Classify publish by pipeline step.
    
    Args:
        publish: Publish dictionary.
        
    Returns:
        Tuple of (department, confidence) or (None, None).
    """
    task = publish.get('task')
    if not task:
        taskStep = publish.get('task.Task.step')
        if taskStep:
            task = {'step': taskStep}
    
    if not task:
        return None, None
    
    step = task.get('step')
    if not step:
        return None, None
    
    if isinstance(step, dict):
        stepName = step.get('name', '')
    else:
        stepName = str(step)
    
    stepBase = stepName.split(' ')[0] if ' ' in stepName else stepName
    
    dept = STEP_TO_DEPT.get(stepBase)
    if dept:
        return dept, 'HIGH'
    
    return None, None


def classifyPublishByTankType(publish):
    """Classify publish by tank type.
    
    Args:
        publish: Publish dictionary.
        
    Returns:
        Tuple of (department, confidence) or (None, None).
    """
    tankType = publish.get('tank_type')
    if not tankType:
        return None, None
    
    if isinstance(tankType, dict):
        tankTypeName = tankType.get('name', '')
    else:
        tankTypeName = str(tankType)
    
    tankTypeLower = tankTypeName.lower()
    
    code = (publish.get('code') or '').lower()
    
    if tankTypeLower in ['usdsublayer', 'usdlayerstack', 'usdpayloadpackage']:
        if '.shd.' in code or code.startswith('shd.'):
            return 'shading', 'MED'
    
    dept = TANK_TYPE_TO_DEPT.get(tankTypeLower)
    if dept:
        return dept, 'MED'
    
    return None, None


def classifyPublishByPattern(publish):
    """Classify publish by code/name patterns.
    
    Args:
        publish: Publish dictionary.
        
    Returns:
        Tuple of (department, confidence) or (None, None).
    """
    code = (publish.get('code') or '').lower()
    name = (publish.get('name') or '').lower()
    text = f"{code} {name}"
    
    for dept, patterns in PATTERN_TO_DEPT.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return dept, 'LOW'
    
    return None, None


def classifyPublish(publish):
    """Classify publish using cascade: step > tank_type > pattern.
    
    Args:
        publish: Publish dictionary.
        
    Returns:
        Tuple of (department, confidence, reason).
    """
    dept, confidence = classifyPublishByStep(publish)
    if dept:
        return dept, confidence, 'step'
    
    dept, confidence = classifyPublishByTankType(publish)
    if dept:
        return dept, confidence, 'tank_type'
    
    dept, confidence = classifyPublishByPattern(publish)
    if dept:
        return dept, confidence, 'pattern'
    
    return 'unclassified', 'LOW', 'unclassified'


def buildSortKey(publish):
    """Build deterministic sort key for publish.
    
    Sort order: (version_number DESC, created_at DESC, id DESC)
    
    Args:
        publish: Publish dictionary.
        
    Returns:
        Tuple of (version, created_at, id).
    """
    version = normalizeVersion(publish)
    createdAt = parseDateTime(publish.get('created_at'))
    publishId = publish.get('id', 0)
    
    return (version, createdAt, publishId)


def resolveGlobalLatest(candidates):
    """Resolve global latest publish from all candidates.
    
    Args:
        candidates: List of publish dictionaries.
        
    Returns:
        Latest publish or None.
    """
    if not candidates:
        return None
    
    return max(candidates, key=buildSortKey)


def detectDuplicates(publishes):
    """Detect duplicate publishes (same version_number).
    
    Args:
        publishes: List of publish dictionaries.
        
    Returns:
        Dict mapping version_number to list of publishes.
    """
    versionGroups = {}
    
    for pub in publishes:
        version = normalizeVersion(pub)
        if version not in versionGroups:
            versionGroups[version] = []
        versionGroups[version].append(pub)
    
    duplicates = {
        version: pubs
        for version, pubs in versionGroups.items()
        if len(pubs) > 1
    }
    
    return duplicates


def resolveDeptBucket(dept, candidates, globalLatest):
    """Resolve publish for a department bucket.
    
    Args:
        dept: Department name.
        candidates: List of publish dictionaries.
        globalLatest: Global latest publish (fallback).
        
    Returns:
        Dictionary with publish info and metadata.
    """
    deptCandidates = []
    
    for pub in candidates:
        if isNoisePublish(pub):
            continue
        
        pubDept, confidence, reason = classifyPublish(pub)
        if pubDept == dept:
            deptCandidates.append({
                'publish': pub,
                'confidence': confidence,
                'reason': reason
            })
    
    if deptCandidates:
        latest = max(deptCandidates, key=lambda item: buildSortKey(item['publish']))
        pub = latest['publish']
        
        duplicates = detectDuplicates([item['publish'] for item in deptCandidates])
        hasDuplicates = len(duplicates) > 0
        
        return {
            'publish_id': pub.get('id'),
            'version': normalizeVersion(pub),
            'dept_status': 'available',
            'is_real_dept': True,
            'classification_reason': latest['reason'],
            'confidence': latest['confidence'],
            'sort_key': buildSortKey(pub),
            'has_duplicates': hasDuplicates,
            'duplicate_count': len(duplicates),
            'publish': pub
        }
    
    if globalLatest:
        return {
            'publish_id': globalLatest.get('id'),
            'version': normalizeVersion(globalLatest),
            'dept_status': 'missing',
            'is_real_dept': False,
            'classification_reason': 'global_latest',
            'confidence': 'LOW',
            'sort_key': buildSortKey(globalLatest),
            'has_duplicates': False,
            'duplicate_count': 0,
            'publish': globalLatest
        }
    
    return {
        'publish_id': -1,
        'version': 0,
        'dept_status': 'not_started',
        'is_real_dept': False,
        'classification_reason': 'no_publishes',
        'confidence': 'LOW',
        'sort_key': (0, datetime.min, -1),
        'has_duplicates': False,
        'duplicate_count': 0,
        'publish': None
    }


def resolveLatestPerDept(sg, assetId):
    """Resolve latest publish per department for an asset.
    
    Main entry point. Returns structured result for all departments.
    
    Args:
        sg: ShotGrid connection.
        assetId: Asset entity ID.
        
    Returns:
        Dictionary mapping department to publish info.
    """
    candidates = fetchCandidates(sg, assetId)
    
    validCandidates = [pub for pub in candidates if not isNoisePublish(pub)]
    
    globalLatest = resolveGlobalLatest(validCandidates)
    
    results = {}
    
    for dept in DEPARTMENTS:
        results[dept] = resolveDeptBucket(dept, validCandidates, globalLatest)
    
    return results


def buildDebugMetadata(results):
    """Build debug metadata for resolver output.
    
    Args:
        results: Dictionary from resolveLatestPerDept.
        
    Returns:
        Debug metadata dictionary.
    """
    metadata = {
        'total_departments': len(DEPARTMENTS),
        'available_departments': 0,
        'missing_departments': 0,
        'not_started_departments': 0,
        'departments_with_duplicates': 0,
        'total_duplicates': 0
    }
    
    for dept, info in results.items():
        status = info.get('dept_status')
        if status == 'available':
            metadata['available_departments'] += 1
        elif status == 'missing':
            metadata['missing_departments'] += 1
        elif status == 'not_started':
            metadata['not_started_departments'] += 1
        
        if info.get('has_duplicates'):
            metadata['departments_with_duplicates'] += 1
            metadata['total_duplicates'] += info.get('duplicate_count', 0)
    
    return metadata
