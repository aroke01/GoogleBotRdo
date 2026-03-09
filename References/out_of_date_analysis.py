"""Out-of-date content analysis for Phase 1.

Computes baselines (latest, available, approved) for upstream asset publishes
and determines verdicts (Current, Out-of-date, Unknown) per policy contract.

Note: This module uses USD files when available for shot analysis.
For asset-only queries without USD context, use asset_resolver directly.
"""

from sg_core import fetchVersion
from sg_utils import SG_PUB_FIELDS
import asset_resolver
import payload_parser

# Phase 1 asset types in scope - essential types only
PHASE1_ASSET_TYPES = {
    'model',
    'geometry',  # Base model geometry (NOT deformedGeometry which is animated cache)
    'texture',
    'lookdev',
    'shading',
    'rig',
    'groom',
    'environment'
}

# Statuses that mean "released for downstream use"
AVAILABLE_STATUSES = {'apr', 'psh'}

# Statuses to omit from baseline calculations
OMIT_STATUSES = {'void', 'del', 'bid', 'omt', 'hld'}

# Tank type name mappings for comprehensive queries
TANK_TYPE_NAMES = {
    'model': ['model'],
    'texture': ['texture', 'textureBundle', 'textureBundle2'],
    'lookdev': ['lookdev', 'shading'],
    'rig': ['rig'],
    'groom': ['groom', 'yeti']
}


def isPhase1AssetType(tankType):
    """Check if tank_type is in Phase 1 scope.

    Args:
        tankType: tank_type.name string from ShotGrid

    Returns:
        True if in scope, False otherwise
    """
    if not tankType:
        return False
    tankTypeLower = tankType.lower()
    
    # Exclude animated caches (deformedGeometry, geometry.cache, groom.cache)
    if 'deformed' in tankTypeLower or '.cache' in tankTypeLower:
        return False
    
    return any(assetType in tankTypeLower for assetType in PHASE1_ASSET_TYPES)


def normalizePhase1TankType(pub):
    """Normalize ShotGrid publish tank type into Phase 1 display categories.

    This is used to ensure the assets-only page can show shading publishes that
    come through as USD-related tank types (e.g. usdSublayer) but have shading
    content encoded in their publish code (e.g. shd.defVariant.*).

    Args:
        pub: TankPublishedFile dict.

    Returns:
        str|None: normalized tank type string used for grouping/display.
    """
    tankType = (pub.get('tank_type') or {}).get('name')
    if not tankType:
        return None

    tankTypeLower = tankType.lower()
    pubCode = pub.get('code') or ''
    pubCodeLower = pubCode.lower()

    if isPhase1AssetType(tankType):
        return tankType

    if tankTypeLower in {'usdsublayer', 'usdlayerstack', 'usdpayloadpackage'}:
        if pubCodeLower.startswith('shd.') or '.shd.' in pubCodeLower:
            return 'shading'

    return None


def computeBaselinesForPublish(sg, publish, preloadedPublishes=None):
    """Compute latest/available/approved baselines for a publish.

    Args:
        sg: ShotGrid connection
        publish: TankPublishedFile dict with id, code, entity, tank_type
        preloadedPublishes: Optional list of already fetched publishes for this asset.

    Returns:
        dict with keys: latest, available, approved (each a dict or None)
    """
    publishId = publish.get('id')
    entityId = (publish.get('entity') or {}).get('id')
    tankTypeId = (publish.get('tank_type') or {}).get('id')
    publishCode = publish.get('code', 'unknown')
    tankTypeName = (publish.get('tank_type') or {}).get('name', 'unknown')

    if not entityId or not tankTypeId:
        return {'latest': None, 'available': None, 'approved': None}

    publishCodePrefix = publishCode.rsplit('_v', 1)[0] if '_v' in publishCode else publishCode
    
    if preloadedPublishes is not None:
        allVersions = []
        for candidatePublish in preloadedPublishes:
            candidateEntityId = (candidatePublish.get('entity') or {}).get('id')
            candidateTankTypeId = (candidatePublish.get('tank_type') or {}).get('id')
            candidateStatus = candidatePublish.get('sg_status_list')
            candidateCode = candidatePublish.get('code', '')
            if candidateEntityId != entityId:
                continue
            if candidateTankTypeId != tankTypeId:
                continue
            if candidateStatus in OMIT_STATUSES:
                continue
            if not candidateCode.startswith(publishCodePrefix):
                continue
            allVersions.append(candidatePublish)
        allVersions.sort(key=lambda item: item.get('version_number', 0), reverse=True)
    else:
        filters = [
            ['entity', 'is', {'type': 'Asset', 'id': entityId}],
            ['tank_type', 'is', {'type': 'TankType', 'id': tankTypeId}],
            ['sg_status_list', 'not_in', list(OMIT_STATUSES)],
            ['code', 'starts_with', publishCodePrefix]
        ]

        fields = ['id', 'code', 'version_number', 'sg_status_list', 'created_at', 'created_by']

        allVersions = sg.find('TankPublishedFile', filters, fields, order=[{'field_name': 'version_number', 'direction': 'desc'}])

    if not allVersions:
        return {'latest': None, 'available': None, 'approved': None}

    latest = allVersions[0]

    availableVersions = [v for v in allVersions if v.get('sg_status_list') in AVAILABLE_STATUSES]
    available = availableVersions[0] if availableVersions else None

    approvedVersions = [v for v in allVersions if v.get('sg_status_list') == 'apr']
    approved = approvedVersions[0] if approvedVersions else None

    print(f"[BASELINE DEBUG] {publishCode} ({tankTypeName}):")
    print(f"  Found {len(allVersions)} total versions")
    print(f"  Latest: v{latest.get('version_number')} ({latest.get('sg_status_list')})")
    if available:
        print(f"  Available (apr/psh): v{available.get('version_number')} ({available.get('sg_status_list')})")
    else:
        print(f"  Available (apr/psh): None")
    if approved:
        print(f"  Approved (apr): v{approved.get('version_number')}")
    
    aprPshVersions = [(v.get('version_number'), v.get('sg_status_list'), v.get('code')) for v in allVersions if v.get('sg_status_list') in AVAILABLE_STATUSES]
    if len(aprPshVersions) > 3:
        print(f"  All apr/psh versions (showing first 5): {aprPshVersions[:5]}")
    else:
        print(f"  All apr/psh versions: {aprPshVersions}")

    return {
        'latest': latest,
        'available': available,
        'approved': approved
    }


def computeVerdict(usedVersionNumber, availableVersionNumber, latestVersionNumber):
    """Compute verdict: compare used vs (apr/psh OR latest).

    Args:
        usedVersionNumber: version_number of used publish (int or None)
        availableVersionNumber: version_number of approved/pushed baseline (int or None)
        latestVersionNumber: version_number of latest baseline (int or None)

    Returns:
        str: 'Current', 'Out-of-date', or 'Unknown'
    
    Logic:
        - If an apr/psh version exists, compare used vs apr/psh (released)
        - If no apr/psh exists, compare used vs latest (any status)
    """
    if usedVersionNumber is None:
        return 'Unknown'

    if availableVersionNumber is None:
        if latestVersionNumber is None:
            return 'Unknown'

        if usedVersionNumber >= latestVersionNumber:
            return 'Current'

        return 'Out-of-date'

    if usedVersionNumber >= availableVersionNumber:
        return 'Current'

    return 'Out-of-date'


def extractAssetNamesFromLayerStackReport(sg, shotId, versionCode):
    """Extract asset names from USD layer stack reports.

    Args:
        sg: ShotGrid connection.
        shotId: Shot ID to query layer stacks for.
        versionCode: Version code string for step filtering.

    Returns:
        set: Asset name strings extracted from the report.
    """
    import json
    import os
    import re
    import ssl

    if not shotId:
        return set()

    versionStep = None
    stepMatch = re.search(r'^[^.]+\.([a-z]+)\.', versionCode or '')
    if stepMatch:
        versionStep = stepMatch.group(1)

    baseStep = versionStep
    if versionStep and versionStep.startswith('qc'):
        baseStep = versionStep[2:]

    filters = [
        ['entity.Shot.id', 'is', shotId],
        ['tank_type.TankType.code', 'is', 'usdLayerStack']
    ]

    if baseStep:
        filters.append(['code', 'contains', f'{baseStep}.'])

    try:
        layerStacks = sg.find('TankPublishedFile', filters, SG_PUB_FIELDS, order=[{'field_name': 'version_number', 'direction': 'desc'}])
    except ssl.SSLError as sslErr:
        print(f"[SSL ERROR] LayerStack fallback query failed: {sslErr}")
        return set()
    except Exception as err:
        print(f"[ERROR] LayerStack fallback query failed: {err}")
        return set()

    if not layerStacks:
        return set()

    layerStackPath = layerStacks[0].get('path', {}).get('local_path') or layerStacks[0].get('sg_path', '')
    if not layerStackPath:
        return set()

    if os.path.isfile(layerStackPath):
        layerStackDir = os.path.dirname(layerStackPath)
    else:
        layerStackDir = layerStackPath

    reportDir = os.path.join(layerStackDir, 'report')
    if not os.path.exists(reportDir):
        return set()

    reportFiles = [reportFile for reportFile in os.listdir(reportDir) if reportFile.endswith('.json')]
    if not reportFiles:
        return set()

    reportPath = os.path.join(reportDir, reportFiles[0])
    try:
        with open(reportPath, 'r') as reportFile:
            reportData = json.load(reportFile)
    except Exception as err:
        print(f"[OUT-OF-DATE COMPREHENSIVE] Error reading layerStack report: {err}")
        return set()

    assetPattern = re.compile(r"<PublishedFile context='<Asset project='[^']+' name='([^']+)'>', publishName='([^']+)', publishType='([^']+)', version='v(\d+)' published>")
    assetNames = set()

    def extractNames(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == '_value' and isinstance(value, str):
                    match = assetPattern.search(value)
                    if match:
                        assetNames.add(match.group(1))
                extractNames(value)
        elif isinstance(obj, list):
            for item in obj:
                extractNames(item)

    extractNames(reportData)
    return assetNames


def getAssetIdToNameFromLayerStackReport(sg, shotId, versionCode, projectId):
    """Resolve asset IDs from layer stack report asset names.

    Args:
        sg: ShotGrid connection.
        shotId: Shot ID to query layer stacks for.
        versionCode: Version code string for step filtering.
        projectId: Project ID for scoped asset lookup.

    Returns:
        dict: Mapping of asset ID to asset code.
    """
    import ssl

    assetNames = extractAssetNamesFromLayerStackReport(sg, shotId, versionCode)
    if not assetNames:
        return {}

    filters = [['code', 'in', list(assetNames)]]
    if projectId:
        filters.append(['project.Project.id', 'is', projectId])

    try:
        assetRecords = sg.find('Asset', filters, ['id', 'code'])
    except ssl.SSLError as sslErr:
        print(f"[SSL ERROR] LayerStack asset query failed: {sslErr}")
        return {}
    except Exception as err:
        print(f"[ERROR] LayerStack asset query failed: {err}")
        return {}

    return {asset.get('id'): asset.get('code') for asset in assetRecords}


def parseRigVersionsFromSubmissionNote(submissionNote):
    """Parse rig versions from Version submission note.

    Extracts lines like:
    - creTrummer_001 - creTrummer.anim.rigVariant3.all_v10
    - prpNolmenStaff_001 - prpNolmenStaff.anim.rigVariant0.all_v1
    
    Also supports legacy format:
    creTrummer_001 - v14 (OUTDATED, the latest approved version is v17)

    Args:
        submissionNote: sg_description field from Version entity

    Returns:
        dict mapping (assetName, publishType) to version number
    """
    import re
    
    rigReferences = {}
    
    if not submissionNote:
        return rigReferences
    
    # Pattern 1: assetName_001 - assetName.anim.rigVariant.all_vN
    rigPattern1 = re.compile(r'([a-zA-Z0-9_]+)_\d+\s+-\s+[a-zA-Z0-9_]+\.anim\.rigVariant\d+\.all_v(\d+)')
    # Pattern 2: assetName_001 - vN (legacy format)
    rigPattern2 = re.compile(r'([a-zA-Z0-9_]+)_\d+\s+-\s+v(\d+)')
    
    inRigSection = False
    for line in submissionNote.split('\n'):
        if 'Rig Versions:' in line:
            inRigSection = True
            continue
        
        if inRigSection:
            if line.strip():
                if line.startswith('['):
                    break
                
                # Try pattern 1 first (new format)
                match = rigPattern1.search(line)
                if match:
                    assetName = match.group(1)
                    versionNum = int(match.group(2))
                    key = (assetName, 'rig')
                    rigReferences[key] = versionNum
                    print(f"[OUT-OF-DATE] Parsed rig: {assetName} v{versionNum}")
                    continue
                
                # Try pattern 2 (legacy format)
                match = rigPattern2.search(line)
                if match:
                    assetName = match.group(1)
                    versionNum = int(match.group(2))
                    key = (assetName, 'rig')
                    rigReferences[key] = versionNum
                    print(f"[OUT-OF-DATE] Parsed rig (legacy): {assetName} v{versionNum}")
    
    return rigReferences


def analyzeOutOfDateContentComprehensive(sg, versionId):
    """Comprehensive out-of-date analysis querying essential asset types.
    
    Queries only essential asset types (model, texture, shading, rig, groom, environment)
    for every asset in the manifest. Excludes noise like geometry caches
    and cameras which change frequently and aren't relevant for asset version tracking.
    
    Args:
        sg: ShotGrid connection
        versionId: Version ID to analyze
    
    Returns:
        dict with:
            - items: list of out-of-date items only
            - allItems: list of all assets with complete metadata
            - summary: dict with counts
    """
    print(f"[OUT-OF-DATE COMPREHENSIVE] Starting comprehensive analysis for version {versionId}")
    
    version = fetchVersion(sg, versionId)
    if not version:
        print(f"[OUT-OF-DATE COMPREHENSIVE] Version {versionId} not found")
        return {
            "items": [],
            "allItems": [],
            "summary": {"total": 0, "outOfDate": 0, "current": 0, "unknown": 0},
            "error": f"Version {versionId} not found"
        }
    
    entity = version.get('entity')
    if not entity or entity.get('type') != 'Shot':
        print(f"[OUT-OF-DATE COMPREHENSIVE] Version entity is not a Shot")
        return {"items": [], "allItems": [], "summary": {"total": 0, "outOfDate": 0, "current": 0, "unknown": 0}}
    
    shotId = entity.get('id')
    print(f"[OUT-OF-DATE COMPREHENSIVE] Analyzing Shot ID {shotId}")
    
    import re
    import ssl
    
    # Get USD Manifest to find which assets are in the shot
    filters = [
        ['entity.Shot.id', 'is', shotId],
        ['tank_type.TankType.code', 'is', 'usdManifest']
    ]
    
    try:
        manifests = sg.find('TankPublishedFile', filters, SG_PUB_FIELDS, order=[{'field_name': 'version_number', 'direction': 'desc'}])
    except ssl.SSLError as sslErr:
        print(f"[SSL ERROR] Manifest query failed: {sslErr}")
        return {
            "items": [],
            "allItems": [],
            "summary": {"total": 0, "outOfDate": 0, "current": 0, "unknown": 0},
            "error": "SSL error fetching manifest"
        }
    except Exception as err:
        print(f"[ERROR] Manifest query failed: {err}")
        return {
            "items": [],
            "allItems": [],
            "summary": {"total": 0, "outOfDate": 0, "current": 0, "unknown": 0},
            "error": f"Error fetching manifest: {str(err)}"
        }
    
    if not manifests:
        print(f"[OUT-OF-DATE COMPREHENSIVE] No usdManifest found")
        return {'items': [], 'allItems': [], 'summary': {'total': 0, 'outOfDate': 0, 'current': 0, 'unknown': 0}}
    
    manifestPub = manifests[0]
    manifestPath = manifestPub.get('path', {}).get('local_path') or manifestPub.get('sg_path', '')
    
    if not manifestPath:
        print(f"[OUT-OF-DATE COMPREHENSIVE] No path for manifest")
        return {
            'items': [], 
            'allItems': [], 
            'summary': {'total': 0, 'outOfDate': 0, 'current': 0, 'unknown': 0},
            'error': 'No manifest path found in ShotGrid'
        }
    
    print(f"[OUT-OF-DATE COMPREHENSIVE] Manifest path: {manifestPath}")
    
    # Extract asset IDs from manifest
    assetIds = set()
    try:
        with open(manifestPath, 'r') as f:
            content = f.read()
        matches = re.findall(r'int rdo_assetId = (\d+)', content)
        assetIds = set(int(aid) for aid in matches)
        print(f"[OUT-OF-DATE COMPREHENSIVE] Extracted {len(assetIds)} asset IDs from manifest")
    except FileNotFoundError as e:
        errorMsg = f"Manifest file not accessible: {manifestPath}"
        print(f"[OUT-OF-DATE COMPREHENSIVE] {errorMsg}")
        return {
            'items': [], 
            'allItems': [], 
            'summary': {'total': 0, 'outOfDate': 0, 'current': 0, 'unknown': 0},
            'error': errorMsg
        }
    except Exception as e:
        errorMsg = f"Error reading manifest at {manifestPath}: {str(e)}"
        print(f"[OUT-OF-DATE COMPREHENSIVE] {errorMsg}")
        return {
            'items': [], 
            'allItems': [], 
            'summary': {'total': 0, 'outOfDate': 0, 'current': 0, 'unknown': 0},
            'error': errorMsg
        }
    
    if not assetIds:
        print(f"[OUT-OF-DATE COMPREHENSIVE] No assets found in manifest")
        assetIdToName = getAssetIdToNameFromLayerStackReport(
            sg,
            shotId,
            version.get('code'),
            (version.get('project') or {}).get('id')
        )
        if not assetIdToName:
            print(f"[OUT-OF-DATE COMPREHENSIVE] Layer stack report fallback failed, querying ShotGrid for upstream asset publishes")
            try:
                filters = [
                    ['entity.Shot.id', 'is', shotId],
                    ['sg_status_list', 'not_in', list(OMIT_STATUSES)]
                ]
                shotPublishes = sg.find('TankPublishedFile', filters, ['id', 'upstream_tank_published_files'])
                
                upstreamPubIds = set()
                for pub in shotPublishes:
                    upstreams = pub.get('upstream_tank_published_files') or []
                    for upstream in upstreams:
                        upstreamPubIds.add(upstream.get('id'))
                
                print(f"[OUT-OF-DATE COMPREHENSIVE] Found {len(upstreamPubIds)} upstream publishes")
                
                if upstreamPubIds:
                    upstreamPubs = sg.find('TankPublishedFile', [['id', 'in', list(upstreamPubIds)]], ['entity'])
                    
                    assetEntityIds = set()
                    for pub in upstreamPubs:
                        entity = pub.get('entity')
                        if entity and entity.get('type') == 'Asset':
                            assetEntityIds.add(entity.get('id'))
                    
                    print(f"[OUT-OF-DATE COMPREHENSIVE] Found {len(assetEntityIds)} unique assets in upstream publishes")
                    
                    if assetEntityIds:
                        assetRecords = sg.find('Asset', [['id', 'in', list(assetEntityIds)]], ['id', 'code'])
                        assetIdToName = {asset.get('id'): asset.get('code') for asset in assetRecords}
                        print(f"[OUT-OF-DATE COMPREHENSIVE] Asset names: {list(assetIdToName.values())}")
                    else:
                        print(f"[OUT-OF-DATE COMPREHENSIVE] No asset entities found in upstream publishes")
                        return {'items': [], 'allItems': [], 'summary': {'total': 0, 'outOfDate': 0, 'current': 0, 'unknown': 0}}
                else:
                    print(f"[OUT-OF-DATE COMPREHENSIVE] No upstream publishes found")
                    return {'items': [], 'allItems': [], 'summary': {'total': 0, 'outOfDate': 0, 'current': 0, 'unknown': 0}}
            except Exception as err:
                print(f"[ERROR] ShotGrid upstream query failed: {err}")
                return {'items': [], 'allItems': [], 'summary': {'total': 0, 'outOfDate': 0, 'current': 0, 'unknown': 0}}

        print(f"[OUT-OF-DATE COMPREHENSIVE] Fallback asset count from layerStack: {len(assetIdToName)}")
        assetIds = set(assetIdToName.keys())
    else:
        # Get asset records
        try:
            assetRecords = sg.find('Asset', [['id', 'in', list(assetIds)]], ['id', 'code'])
            assetIdToName = {asset.get('id'): asset.get('code') for asset in assetRecords}
        except ssl.SSLError as sslErr:
            print(f"[SSL ERROR] Asset query failed: {sslErr}")
            return {
                "items": [],
                "allItems": [],
                "summary": {"total": 0, "outOfDate": 0, "current": 0, "unknown": 0},
                "error": "SSL error fetching assets"
            }
        except Exception as err:
            print(f"[ERROR] Asset query failed: {err}")
            return {
                "items": [],
                "allItems": [],
                "summary": {"total": 0, "outOfDate": 0, "current": 0, "unknown": 0},
                "error": f"Error fetching assets: {str(err)}"
            }

        if not assetIdToName:
            print("[OUT-OF-DATE COMPREHENSIVE] Asset records empty, falling back to layerStack")
            assetIdToName = getAssetIdToNameFromLayerStackReport(
                sg,
                shotId,
                version.get('code'),
                (version.get('project') or {}).get('id')
            )
            if not assetIdToName:
                return {'items': [], 'allItems': [], 'summary': {'total': 0, 'outOfDate': 0, 'current': 0, 'unknown': 0}}
            assetIds = set(assetIdToName.keys())
    
    print(f"[OUT-OF-DATE COMPREHENSIVE] Found {len(assetIdToName)} assets")
    
    # Query ALL Phase 1 asset types for each asset
    entityResults = {}
    fieldsWithUser = list(set(SG_PUB_FIELDS + ['created_by', 'created_at']))
    
    for assetId, assetName in assetIdToName.items():
        print(f"[OUT-OF-DATE COMPREHENSIVE] Querying all Phase 1 types for asset: {assetName}")
        
        # Query all publishes for this asset
        filters = [
            ['entity.Asset.id', 'is', assetId],
            ['sg_status_list', 'not_in', list(OMIT_STATUSES)]
        ]
        
        try:
            assetPublishes = sg.find('TankPublishedFile', filters, fieldsWithUser)
        except ssl.SSLError as sslErr:
            print(f"[SSL ERROR] Asset publishes query failed for {assetName}: {sslErr}")
            continue
        except Exception as err:
            print(f"[ERROR] Asset publishes query failed for {assetName}: {err}")
            continue
        
        # Group by tank type
        publishesByType = {}
        allTankTypes = set()
        for pub in assetPublishes:
            tankType = (pub.get('tank_type') or {}).get('name')
            if tankType:
                allTankTypes.add(tankType)
            normalizedTankType = normalizePhase1TankType(pub)
            if normalizedTankType:
                if normalizedTankType not in publishesByType:
                    publishesByType[normalizedTankType] = []
                publishesByType[normalizedTankType].append(pub)
        
        print(f"[OUT-OF-DATE COMPREHENSIVE] Asset {assetName}: found tank types: {allTankTypes}")
        print(f"[OUT-OF-DATE COMPREHENSIVE] Asset {assetName}: Phase 1 types matched: {list(publishesByType.keys())}")
        
        # Process each Phase 1 type found
        for tankType, pubs in publishesByType.items():
            # Sort by version number descending
            pubs.sort(key=lambda p: p.get('version_number', 0), reverse=True)
            
            print(f"[OUT-OF-DATE COMPREHENSIVE] {assetName} ({tankType}): Found {len(pubs)} publishes")
            pubVersions = [(p.get('version_number'), p.get('sg_status_list'), p.get('code')) for p in pubs[:5]]
            print(f"[OUT-OF-DATE COMPREHENSIVE] {assetName} ({tankType}): Top 5 versions: {pubVersions}")
            
            latestPub = pubs[0]
            
            baselines = computeBaselinesForPublish(sg, latestPub, preloadedPublishes=assetPublishes)
            availableBaseline = baselines.get('available')
            availableVersionNumber = availableBaseline.get('version_number') if availableBaseline else None
            latestBaseline = baselines.get('latest')
            latestVersionNumber = latestBaseline.get('version_number') if latestBaseline else None
            
            usedVersionNumber = latestPub.get('version_number')
            verdict = computeVerdict(usedVersionNumber, availableVersionNumber, latestVersionNumber)
            
            usedCreatedBy = latestPub.get('created_by', {})
            usedCreatedByName = usedCreatedBy.get('name') if isinstance(usedCreatedBy, dict) else None
            usedCreatedAt = latestPub.get('created_at')
            usedStatus = latestPub.get('sg_status_list')
            
            availableCreatedBy = availableBaseline.get('created_by', {}) if availableBaseline else {}
            availableCreatedByName = availableCreatedBy.get('name') if isinstance(availableCreatedBy, dict) else None
            availableCreatedAt = availableBaseline.get('created_at') if availableBaseline else None
            availableStatus = availableBaseline.get('sg_status_list') if availableBaseline else None
            
            latestCreatedBy = latestBaseline.get('created_by', {}) if latestBaseline else {}
            latestCreatedByName = latestCreatedBy.get('name') if isinstance(latestCreatedBy, dict) else None
            latestCreatedAt = latestBaseline.get('created_at') if latestBaseline else None
            latestStatus = latestBaseline.get('sg_status_list') if latestBaseline else None
            
            approvedBaseline = baselines.get('approved')
            approvedCreatedBy = approvedBaseline.get('created_by', {}) if approvedBaseline else {}
            approvedCreatedByName = approvedCreatedBy.get('name') if isinstance(approvedCreatedBy, dict) else None
            approvedCreatedAt = approvedBaseline.get('created_at') if approvedBaseline else None
            approvedStatus = approvedBaseline.get('sg_status_list') if approvedBaseline else None
            
            key = f"{assetId}_{tankType}"
            entityResults[key] = {
                'publishId': latestPub.get('id'),
                'name': f"{assetName}.{tankType}.v{usedVersionNumber}",
                'entityName': assetName,
                'entityId': assetId,
                'tankType': tankType,
                'usedVersion': usedVersionNumber,
                'usedCreatedBy': usedCreatedByName,
                'usedCreatedAt': usedCreatedAt,
                'usedStatus': usedStatus,
                'availableVersion': availableVersionNumber,
                'availableCreatedBy': availableCreatedByName,
                'availableCreatedAt': availableCreatedAt,
                'availableStatus': availableStatus,
                'latestVersion': latestVersionNumber,
                'latestCreatedBy': latestCreatedByName,
                'latestCreatedAt': latestCreatedAt,
                'latestStatus': latestStatus,
                'approvedVersion': (baselines.get('approved') or {}).get('version_number'),
                'approvedCreatedBy': approvedCreatedByName,
                'approvedCreatedAt': approvedCreatedAt,
                'approvedStatus': approvedStatus,
                'verdict': verdict
            }
            
            print(f"[OUT-OF-DATE COMPREHENSIVE]   - {assetName} ({tankType}) v{usedVersionNumber} [{verdict}]")
    
    # Calculate summary
    counts = {'total': 0, 'outOfDate': 0, 'current': 0, 'unknown': 0}
    for item in entityResults.values():
        verdict = item['verdict']
        counts['total'] += 1
        verdictKey = verdict.lower().replace('-', '')
        counts[verdictKey] = counts.get(verdictKey, 0) + 1
    
    outOfDateItems = [item for item in entityResults.values() if item['verdict'] == 'Out-of-date']
    allItems = list(entityResults.values())
    
    print(f"[OUT-OF-DATE COMPREHENSIVE] Complete: {counts['total']} total, {counts['outOfDate']} out-of-date")
    
    assetPayloads = {}
    for assetId, assetName in assetIdToName.items():
        payloadVersions = payload_parser.parsePayloadVersions(sg, assetName)
        if payloadVersions:
            assetPayloads[assetName] = payloadVersions
            print(f"[OUT-OF-DATE COMPREHENSIVE] Payload for {assetName}: {payloadVersions}")
    
    return {
        'items': outOfDateItems,
        'allItems': allItems,
        'summary': counts,
        'payloads': assetPayloads
    }


def analyzeOutOfDateContent(sg, versionId):
    """Analyze out-of-date content for a version's upstream dependencies.

    Args:
        sg: ShotGrid connection
        versionId: Version ID to analyze

    Returns:
        dict with:
            - items: list of out-of-date items only
            - summary: dict with counts
    """
    print(f"[OUT-OF-DATE] Starting analysis for version {versionId}")
    
    # Fetch the version data with SSL retry logic
    version = fetchVersion(sg, versionId)
    if not version:
        print(f"[OUT-OF-DATE] Version {versionId} not found or fetch failed")
        return {
            "items": [], 
            "allItems": [],
            "summary": {"total": 0, "outOfDate": 0, "current": 0, "unknown": 0},
            "error": f"Version {versionId} not found or unavailable"
        }
    
    print(f"[OUT-OF-DATE] Fetched version: {version.get('code', 'Unknown')}")
    print(f"[OUT-OF-DATE] Version fields: {list(version.keys())}")
    description = version.get('description')
    if description:
        print(f"[OUT-OF-DATE] Description field exists, length: {len(description)}")
    else:
        print(f"[OUT-OF-DATE] Description field MISSING or None")

    entity = version.get('entity')
    if not entity or entity.get('type') != 'Shot':
        print(f"[OUT-OF-DATE] Version entity is not a Shot: {entity}")
        return {"items": [], "summary": {"total": 0, "outOfDate": 0, "current": 0, "unknown": 0}}

    shotId = entity.get('id')
    print(f"[OUT-OF-DATE] Analyzing Shot ID {shotId}")

    import re
    import ssl
    import time
    
    filters = [
        ['entity.Shot.id', 'is', shotId],
        ['tank_type.TankType.code', 'is', 'usdManifest']
    ]
    
    # Wrap manifest query with SSL retry logic
    manifests = None
    maxRetries = 1
    for attempt in range(maxRetries):
        try:
            manifests = sg.find('TankPublishedFile', filters, SG_PUB_FIELDS, order=[{'field_name': 'version_number', 'direction': 'desc'}])
            break
        except ssl.SSLError as sslErr:
            print(f"[SSL ERROR] Manifest query failed for shot {shotId}: {sslErr}")
            return {
                "items": [], 
                "allItems": [],
                "summary": {"total": 0, "outOfDate": 0, "current": 0, "unknown": 0},
                "error": f"SSL error fetching manifest for shot {shotId}"
            }
        except Exception as err:
            print(f"[ERROR] Manifest query failed for shot {shotId}: {err}")
            return {
                "items": [], 
                "allItems": [],
                "summary": {"total": 0, "outOfDate": 0, "current": 0, "unknown": 0},
                "error": f"Error fetching manifest: {str(err)}"
            }
    
    if not manifests:
        print(f"[OUT-OF-DATE] No usdManifest found for Shot")
        return {'items': [], 'summary': {'total': 0, 'outOfDate': 0, 'current': 0, 'unknown': 0}}
    
    manifestPub = manifests[0]
    manifestPath = manifestPub.get('path', {}).get('local_path') or manifestPub.get('sg_path', '')
    
    print(f"[OUT-OF-DATE] Found usdManifest v{manifestPub.get('version_number')}: {manifestPath}")
    
    if not manifestPath:
        print(f"[OUT-OF-DATE] No path for manifest")
        return {'items': [], 'summary': {'total': 0, 'outOfDate': 0, 'current': 0, 'unknown': 0}}
    
    assetIds = set()
    try:
        with open(manifestPath, 'r') as f:
            content = f.read()
        
        matches = re.findall(r'int rdo_assetId = (\d+)', content)
        assetIds = set(int(aid) for aid in matches)
        print(f"[OUT-OF-DATE] Extracted {len(assetIds)} asset IDs from manifest")
        
    except Exception as e:
        print(f"[OUT-OF-DATE] Error reading manifest: {e}")
        return {'items': [], 'summary': {'total': 0, 'outOfDate': 0, 'current': 0, 'unknown': 0}}
    
    if not assetIds:
        print(f"[OUT-OF-DATE] No assets found in manifest")
        return {'items': [], 'summary': {'total': 0, 'outOfDate': 0, 'current': 0, 'unknown': 0}}

    versionCode = version.get('code', '')
    versionStep = None
    
    stepMatch = re.search(r'^[^.]+\.([a-z]+)\.', versionCode)
    if stepMatch:
        versionStep = stepMatch.group(1)
    
    if not versionStep:
        sgStep = version.get('sg_step')
        if sgStep:
            versionStep = sgStep.get('name', '').lower()
    
    # Handle QC versions - strip 'qc' prefix to find the base department layer stack
    # e.g., qcani -> ani, qclay -> lay
    baseStep = versionStep
    if versionStep and versionStep.startswith('qc'):
        baseStep = versionStep[2:]
        print(f"[OUT-OF-DATE] QC version detected: {versionStep} -> using base step: {baseStep}")
    
    print(f"[OUT-OF-DATE] Version code: {versionCode}, extracted step: {versionStep}, base step: {baseStep}")
    
    filters = [
        ['entity.Shot.id', 'is', shotId],
        ['tank_type.TankType.code', 'is', 'usdLayerStack']
    ]
    
    if baseStep:
        filters.append(['code', 'contains', f'{baseStep}.'])
    
    # Wrap layerStack query with SSL error handling
    try:
        layerStacks = sg.find('TankPublishedFile', filters, SG_PUB_FIELDS, order=[{'field_name': 'version_number', 'direction': 'desc'}])
    except ssl.SSLError as sslErr:
        print(f"[SSL ERROR] LayerStack query failed for shot {shotId}: {sslErr}")
        return {
            "items": [], 
            "allItems": [],
            "summary": {"total": 0, "outOfDate": 0, "current": 0, "unknown": 0},
            "error": f"SSL error fetching layerStack for shot {shotId}"
        }
    except Exception as err:
        print(f"[ERROR] LayerStack query failed for shot {shotId}: {err}")
        return {
            "items": [], 
            "allItems": [],
            "summary": {"total": 0, "outOfDate": 0, "current": 0, "unknown": 0},
            "error": f"Error fetching layerStack: {str(err)}"
        }
    
    print(f"[OUT-OF-DATE] Found {len(layerStacks)} usdLayerStack publishes for step '{versionStep}'")
    
    if not layerStacks:
        print(f"[OUT-OF-DATE] No usdLayerStack found for Shot + step")
        return {'items': [], 'summary': {'total': 0, 'outOfDate': 0, 'current': 0, 'unknown': 0}}
    
    layerStackPub = layerStacks[0]
    layerStackPath = layerStackPub.get('path', {}).get('local_path') or layerStackPub.get('sg_path', '')
    print(f"[OUT-OF-DATE] USD Layer Stack v{layerStackPub.get('version_number')}, path: {layerStackPath}")
    
    if not layerStackPath:
        print(f"[OUT-OF-DATE] No path for usdLayerStack")
        return {'items': [], 'summary': {'total': 0, 'outOfDate': 0, 'current': 0, 'unknown': 0}}
    
    import os
    import json
    
    if os.path.isfile(layerStackPath):
        layerStackDir = os.path.dirname(layerStackPath)
    else:
        layerStackDir = layerStackPath
    
    reportDir = os.path.join(layerStackDir, 'report')
    reportFiles = []
    if os.path.exists(reportDir):
        reportFiles = [f for f in os.listdir(reportDir) if f.endswith('.json')]
    
    if not reportFiles:
        print(f"[OUT-OF-DATE] No report JSON found in {reportDir}")
        return {'items': [], 'summary': {'total': 0, 'outOfDate': 0, 'current': 0, 'unknown': 0}}
    
    reportPath = os.path.join(reportDir, reportFiles[0])
    print(f"[OUT-OF-DATE] Reading USD Layer Stack report: {reportPath}")
    
    try:
        with open(reportPath, 'r') as f:
            reportData = json.load(f)
    except Exception as e:
        print(f"[OUT-OF-DATE] Error reading report: {e}")
        return {'items': [], 'summary': {'total': 0, 'outOfDate': 0, 'current': 0, 'unknown': 0}}
    
    assetPattern = re.compile(r"<PublishedFile context='<Asset project='[^']+' name='([^']+)'>', publishName='([^']+)', publishType='([^']+)', version='v(\d+)' published>")
    
    usedAssets = {}
    
    def extractAssetPublishes(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == '_value' and isinstance(value, str):
                    match = assetPattern.search(value)
                    if match:
                        assetName, publishName, publishType, versionStr = match.groups()
                        versionNum = int(versionStr)
                        key = (assetName, publishType)
                        if key not in usedAssets or versionNum > usedAssets[key]:
                            usedAssets[key] = versionNum
                extractAssetPublishes(value)
        elif isinstance(obj, list):
            for item in obj:
                extractAssetPublishes(item)
    
    extractAssetPublishes(reportData)
    print(f"[OUT-OF-DATE] Extracted {len(usedAssets)} asset publishes from USD Layer Stack report")
    
    submissionNote = version.get('description', '')
    print(f"[OUT-OF-DATE] Version ID: {versionId}, Description length: {len(submissionNote)}")
    if len(submissionNote) > 0:
        print(f"[OUT-OF-DATE] Description preview: {submissionNote[:100]}...")
    rigAssetNames = set()
    if submissionNote:
        print(f"[OUT-OF-DATE] Parsing submission note for rig versions")
        rigRefs = parseRigVersionsFromSubmissionNote(submissionNote)
        print(f"[OUT-OF-DATE] Found {len(rigRefs)} rig references")
        
        for (assetName, publishType), usedVersion in rigRefs.items():
            key = (assetName, publishType)
            if key not in usedAssets or usedVersion > usedAssets[key]:
                usedAssets[key] = usedVersion
                rigAssetNames.add(assetName)
                print(f"[OUT-OF-DATE] Added rig from submission note: {assetName} ({publishType}) v{usedVersion}")
    else:
        print(f"[OUT-OF-DATE] No submission note found in version")
    
    # Wrap asset query with SSL error handling
    try:
        assetRecords = sg.find('Asset', [['id', 'in', list(assetIds)]], ['id', 'code'])
        assetNameToId = {asset.get('code'): asset.get('id') for asset in assetRecords}
    except ssl.SSLError as sslErr:
        print(f"[SSL ERROR] Asset query failed: {sslErr}")
        return {
            "items": [], 
            "allItems": [],
            "summary": {"total": 0, "outOfDate": 0, "current": 0, "unknown": 0},
            "error": "SSL error fetching asset records"
        }
    except Exception as err:
        print(f"[ERROR] Asset query failed: {err}")
        return {
            "items": [], 
            "allItems": [],
            "summary": {"total": 0, "outOfDate": 0, "current": 0, "unknown": 0},
            "error": f"Error fetching assets: {str(err)}"
        }
    
    if rigAssetNames:
        print(f"[OUT-OF-DATE] Querying asset IDs for rigs: {rigAssetNames}")
        try:
            rigAssetRecords = sg.find('Asset', [['code', 'in', list(rigAssetNames)], ['project.Project.id', 'is', version.get('project', {}).get('id')]], ['id', 'code'])
            for asset in rigAssetRecords:
                assetNameToId[asset.get('code')] = asset.get('id')
            print(f"[OUT-OF-DATE] Added {len(rigAssetRecords)} rig assets to mapping")
        except ssl.SSLError as sslErr:
            print(f"[SSL ERROR] Rig asset query failed: {sslErr}")
            return {
                "items": [], 
                "allItems": [],
                "summary": {"total": 0, "outOfDate": 0, "current": 0, "unknown": 0},
                "error": "SSL error fetching rig asset records"
            }
        except Exception as err:
            print(f"[ERROR] Rig asset query failed: {err}")
            return {
                "items": [], 
                "allItems": [],
                "summary": {"total": 0, "outOfDate": 0, "current": 0, "unknown": 0},
                "error": f"Error fetching rig assets: {str(err)}"
            }
    
    print(f"[OUT-OF-DATE] Asset name mapping: {assetNameToId}")
    
    allEntities = {}
    counts = {'total': 0, 'outOfDate': 0, 'current': 0, 'unknown': 0}
    
    for (assetName, publishType), usedVersion in usedAssets.items():
        if not isPhase1AssetType(publishType):
            print(f"[OUT-OF-DATE] Skipping non-Phase1 type: {assetName} ({publishType})")
            continue
        
        entityId = assetNameToId.get(assetName)
        if not entityId:
            print(f"[OUT-OF-DATE] Asset name '{assetName}' not found in manifest assets")
            continue
        
        key = (entityId, publishType)
        allEntities[key] = {
            'entityId': entityId,
            'entityName': assetName,
            'tankType': publishType,
            'usedVersion': usedVersion,
            'publishId': None,
            'name': f'{assetName}.{publishType}.v{usedVersion}',
            'usedStatus': None,
            'fullPublish': None
        }
    
    print(f"[OUT-OF-DATE] Collected {len(allEntities)} Phase 1 assets from USD Layer Stack")
    for key, data in allEntities.items():
        entityId, tankType = key
        print(f"[OUT-OF-DATE]   - {data['entityName']} ({tankType}) v{data['usedVersion']}")

    entityResults = {}
    for key, entityData in allEntities.items():
        entityId, tankType = key
        
        if not isPhase1AssetType(tankType):
            continue

        print(f"[OUT-OF-DATE] Phase 1 asset found: {entityData['entityName']} ({tankType}), used v{entityData['usedVersion']}")

        filters = [
            ['entity.Asset.id', 'is', entityId],
            ['sg_status_list', 'not_in', list(OMIT_STATUSES)]
        ]
        
        # Wrap asset publishes query with SSL error handling
        # Need created_by and created_at for complete asset info
        fieldsWithUser = list(set(SG_PUB_FIELDS + ['created_by', 'created_at']))
        try:
            assetPublishes = sg.find('TankPublishedFile', filters, fieldsWithUser)
        except ssl.SSLError as sslErr:
            print(f"[SSL ERROR] Asset publishes query failed for {entityData['entityName']}: {sslErr}")
            continue
        except Exception as err:
            print(f"[ERROR] Asset publishes query failed for {entityData['entityName']}: {err}")
            continue
        
        matchingPublishes = []
        for pub in assetPublishes:
            pubTankType = (pub.get('tank_type') or {}).get('name')
            if pubTankType == tankType:
                matchingPublishes.append(pub)
        
        if not matchingPublishes:
            print(f"[OUT-OF-DATE] No publishes found for {entityData['entityName']} ({tankType})")
            continue
        
        usedPublish = None
        for pub in matchingPublishes:
            if pub.get('version_number') == entityData['usedVersion']:
                usedPublish = pub
                break
        
        if not usedPublish:
            print(f"[OUT-OF-DATE] Could not find used publish v{entityData['usedVersion']} for {entityData['entityName']} ({tankType})")
            usedPublish = matchingPublishes[0] if matchingPublishes else None
        
        if not usedPublish:
            print(f"[OUT-OF-DATE] No matching publish found for {entityData['entityName']} ({tankType})")
            continue
        
        baselines = computeBaselinesForPublish(sg, usedPublish)
        availableBaseline = baselines.get('available')
        availableVersionNumber = availableBaseline.get('version_number') if availableBaseline else None
        latestBaseline = baselines.get('latest')
        latestVersionNumber = latestBaseline.get('version_number') if latestBaseline else None

        verdict = computeVerdict(entityData['usedVersion'], availableVersionNumber, latestVersionNumber)

        usedCreatedBy = usedPublish.get('created_by', {})
        usedCreatedByName = usedCreatedBy.get('name') if isinstance(usedCreatedBy, dict) else None
        usedCreatedAt = usedPublish.get('created_at')
        usedStatus = usedPublish.get('sg_status_list')
        
        availableCreatedBy = availableBaseline.get('created_by', {}) if availableBaseline else {}
        availableCreatedByName = availableCreatedBy.get('name') if isinstance(availableCreatedBy, dict) else None
        availableCreatedAt = availableBaseline.get('created_at') if availableBaseline else None
        availableStatus = availableBaseline.get('sg_status_list') if availableBaseline else None
        
        latestCreatedBy = latestBaseline.get('created_by', {}) if latestBaseline else {}
        latestCreatedByName = latestCreatedBy.get('name') if isinstance(latestCreatedBy, dict) else None
        latestCreatedAt = latestBaseline.get('created_at') if latestBaseline else None
        latestStatus = latestBaseline.get('sg_status_list') if latestBaseline else None
        
        approvedBaseline = baselines.get('approved')
        approvedCreatedBy = approvedBaseline.get('created_by', {}) if approvedBaseline else {}
        approvedCreatedByName = approvedCreatedBy.get('name') if isinstance(approvedCreatedBy, dict) else None
        approvedCreatedAt = approvedBaseline.get('created_at') if approvedBaseline else None
        approvedStatus = approvedBaseline.get('sg_status_list') if approvedBaseline else None

        entityResults[entityId] = {
            'publishId': entityData['publishId'],
            'name': entityData['name'],
            'entityName': entityData['entityName'],
            'entityId': entityId,
            'tankType': tankType,
            'usedVersion': entityData['usedVersion'],
            'usedCreatedBy': usedCreatedByName,
            'usedCreatedAt': usedCreatedAt,
            'usedStatus': usedStatus,
            'availableVersion': availableVersionNumber,
            'availableCreatedBy': availableCreatedByName,
            'availableCreatedAt': availableCreatedAt,
            'availableStatus': availableStatus,
            'latestVersion': latestVersionNumber,
            'latestCreatedBy': latestCreatedByName,
            'latestCreatedAt': latestCreatedAt,
            'latestStatus': latestStatus,
            'approvedVersion': (baselines.get('approved') or {}).get('version_number'),
            'approvedCreatedBy': approvedCreatedByName,
            'approvedCreatedAt': approvedCreatedAt,
            'approvedStatus': approvedStatus,
            'verdict': verdict
        }

    for entityId, item in entityResults.items():
        verdict = item['verdict']
        counts['total'] += 1
        verdictKey = verdict.lower().replace('-', '')
        counts[verdictKey] = counts.get(verdictKey, 0) + 1

    outOfDateItems = [item for item in entityResults.values() if item['verdict'] == 'Out-of-date']
    allItems = list(entityResults.values())

    return {
        'items': outOfDateItems,
        'allItems': allItems,
        'summary': counts
    }
# DEBUG: Production server test - Wed Jan  7 12:44:25 EST 2026
