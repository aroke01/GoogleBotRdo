"""
Asset Pipeline Analyzer

Cross-references ShotGrid approved versions, USD Payload Packages, and Layer Stack
to detect version mismatches in the USD pipeline. Helps artists identify when
containers need rebuilding (buildPayloadPackage, buildLayerStack).

Key systems unified:
1. ShotGrid - approved/published versions per department
2. Payload Package - bundled payloads on filesystem
3. Layer Stack - final composed USD file
4. Filesystem - file existence validation
"""

import os
import re
import sys
import asyncio
import concurrent.futures
from typing import Dict, List, Optional, Tuple, Any

pythonRoot = os.path.dirname(os.path.abspath(__file__))
if pythonRoot not in sys.path:
    sys.path.insert(0, pythonRoot)

import asset_resolver
import payload_parser
import usd_analysis
import geometry_hash_utils
from sg_cache import assetAnalyzerCache
from audits import asset_checks


DEPARTMENTS = ['Model', 'Texture', 'Shading', 'Rig', 'Groom']

DEPT_TO_STEP_MAP = {
    'Model': 'mod',
    'Texture': 'tex',
    'Shading': 'shd',
    'Rig': 'rig',
    'Groom': 'hair'
}

CONFLUENCE_LINKS = {
    'VERSION_MISMATCH': 'https://confluence.rodeofx.com/display/PIPE/Rebuilding+Payload+Packages',
    'LAYERSTACK_STALE': 'https://confluence.rodeofx.com/display/PIPE/Rebuilding+Layer+Stacks',
    'FILE_MISSING': 'https://confluence.rodeofx.com/display/PIPE/File+Access+Troubleshooting',
    'PP_NOT_BUILT': 'https://confluence.rodeofx.com/display/PIPE/Payload+Package+Setup',
    'NO_APPROVED_VERSION': 'https://confluence.rodeofx.com/display/PIPE/Approval+Workflow',
    'MANIFEST_NEWER': 'https://confluence.rodeofx.com/display/PIPE/Manifest+And+LayerStack'
}


MISMATCH_RULE_MAPPING = {
    'PP_NOT_BUILT': 'pp_not_built',
    'VERSION_MISMATCH': 'version_mismatch',
    'VERSION_MISMATCH_CONTENT_STALE': 'version_mismatch_content_stale',
    'VERSION_MISMATCH_CONTENT_OK': 'version_mismatch_content_ok',
    'LAYERSTACK_STALE': 'layerstack_stale',
}


POLICY_RULE_DEPARTMENT = {
    'model_newer_than_rig': 'Rig',
    'model_topology_changed': 'Rig',
    'model_uv_only_changed': 'Rig',
    'texture_newer_than_shading': 'Shading',
    'rig_expected_but_missing': 'Rig',
    'status_mismatch_rig': 'Rig',
    'rig_out_of_date': 'Rig',
}


def normalizeAnalyzerSeverity(severityValue):
    """Map policy severities to analyzer severity vocabulary.

    Args:
        severityValue: Raw severity value from audit rules.

    Returns:
        Analyzer-compatible severity string.
    """
    if severityValue == 'high':
        return 'error'
    if severityValue == 'medium':
        return 'warning'
    if severityValue == 'low':
        return 'info'
    return severityValue or 'info'


def buildMismatchItem(mismatchType, messageText, severityValue, suggestionText=None, confluenceLink=None, extraFields=None):
    """Build normalized mismatch payload with canonical rule metadata.

    Args:
        mismatchType: Legacy mismatch type used by analyzer UI.
        messageText: Human-readable mismatch details.
        severityValue: Severity string.
        suggestionText: Optional remediation suggestion.
        confluenceLink: Optional help URL.
        extraFields: Optional dictionary merged into payload.

    Returns:
        Normalized mismatch dictionary.
    """
    ruleId = MISMATCH_RULE_MAPPING.get(mismatchType)
    ruleMeta = asset_checks.getValidationRule(ruleId) if ruleId else {
        'title': mismatchType,
        'description': messageText,
        'severity': severityValue,
    }
    mismatchItem = {
        'type': mismatchType,
        'ruleId': ruleId,
        'label': ruleMeta.get('title', mismatchType),
        'title': ruleMeta.get('title', mismatchType),
        'severity': severityValue,
        'description': messageText,
        'content': messageText,
        'message': messageText,
        'suggestion': suggestionText,
        'confluenceLink': confluenceLink,
        'ruleCatalogVersion': asset_checks.RULE_CATALOG_VERSION,
    }
    if extraFields:
        mismatchItem.update(extraFields)
    return mismatchItem


def convertPolicyIssueToAnalyzerMismatch(policyIssue):
    """Convert policy issue payload to analyzer mismatch format.

    Args:
        policyIssue: Issue dictionary from audits.asset_checks.

    Returns:
        Analyzer mismatch dictionary.
    """
    issueType = policyIssue.get('type', 'policy_issue')
    ruleId = policyIssue.get('ruleId', issueType)
    labelText = policyIssue.get('title') or policyIssue.get('label', issueType)
    messageText = policyIssue.get('description') or policyIssue.get('content') or labelText
    return {
        'type': issueType.upper(),
        'ruleId': ruleId,
        'label': labelText,
        'title': labelText,
        'severity': normalizeAnalyzerSeverity(policyIssue.get('severity')),
        'description': messageText,
        'content': messageText,
        'message': messageText,
        'suggestion': None,
        'confluenceLink': None,
        'ruleCatalogVersion': policyIssue.get('ruleCatalogVersion', asset_checks.RULE_CATALOG_VERSION),
    }


def getPolicyDepartment(policyIssue):
    """Resolve analyzer department for a policy issue.

    Args:
        policyIssue: Issue dictionary from audits.asset_checks.

    Returns:
        Department display name used by analyzer.
    """
    ruleId = policyIssue.get('ruleId') or policyIssue.get('type')
    return POLICY_RULE_DEPARTMENT.get(ruleId, 'Rig')


def queryAssetByCode(sgConnection, assetCode, showCode=None):
    """Query asset entity by code with caching.
    
    Args:
        sgConnection: ShotGrid API connection.
        assetCode: Asset code (e.g., 'chrNolmen').
        showCode: Optional show/project code to filter by (e.g., 'lbp3').
        
    Returns:
        Dict with asset entity or None.
    """
    filters = [['code', 'is', assetCode]]
    if showCode:
        filters.append(['project.Project.tank_name', 'is', showCode])
    fields = ['id', 'code', 'project']
    
    cacheKey = assetAnalyzerCache.generateKey('Asset', filters, fields)
    cached = assetAnalyzerCache.get(cacheKey)
    if cached is not None:
        print(f"[CACHE HIT] Asset query for {assetCode} (show: {showCode})")
        return cached
    
    assets = sgConnection.find('Asset', filters, fields)
    result = assets[0] if assets else None
    assetAnalyzerCache.set(cacheKey, result)
    return result


def extractShowCode(asset):
    """Extract show code from asset entity.
    
    Args:
        asset: Asset entity dict with project field.
        
    Returns:
        Show code string or None.
    """
    project = asset.get('project')
    if not project or not isinstance(project, dict):
        return None
    
    projectName = project.get('name', '')
    return projectName.lower() if projectName else None


def findLayerStackForAsset(showCode, assetCode):
    """Find latest layer stack file for an asset.
    
    Prioritizes defStep.defVariant (approved/pushed variant) over other variants.
    
    Args:
        showCode: Show/project code (e.g., 'lbp3').
        assetCode: Asset code (e.g., 'chrNolmen').
        
    Returns:
        Dict with version and path, or None.
    """
    basePath = f"/rdo/shows/{showCode}/.published/assets/{assetCode}/usdLayerStack"
    
    if not os.path.exists(basePath):
        return None
    
    try:
        defVariantPath = os.path.join(basePath, 'defStep.defVariant')
        
        if os.path.exists(defVariantPath):
            versionPaths = {}
            
            for root, dirs, files in os.walk(defVariantPath):
                for dirName in dirs:
                    versionMatch = re.match(r'^v(\d+)$', dirName)
                    if versionMatch:
                        versionNum = int(versionMatch.group(1))
                        fullPath = os.path.join(root, dirName)
                        versionPaths[versionNum] = fullPath
            
            if versionPaths:
                latestVersion = max(versionPaths.keys())
                return {
                    'version': latestVersion,
                    'path': versionPaths[latestVersion]
                }
        
        print(f"[DEBUG] defStep.defVariant not found for {assetCode}, checking other variants")
        
        versionPaths = {}
        for root, dirs, files in os.walk(basePath):
            for dirName in dirs:
                versionMatch = re.match(r'^v(\d+)$', dirName)
                if versionMatch:
                    versionNum = int(versionMatch.group(1))
                    fullPath = os.path.join(root, dirName)
                    versionPaths[versionNum] = fullPath
        
        if versionPaths:
            latestVersion = max(versionPaths.keys())
            return {
                'version': latestVersion,
                'path': versionPaths[latestVersion]
            }
        
        return None
        
    except Exception as error:
        print(f"[ERROR] Failed to scan layer stack directory: {error}")
        return None


def classifyDepartmentFromPayloadPath(payloadPath):
    """Classify department from payload package or sublayer path.
    
    Handles both direct paths (/geometry/, /rig/) and usdPayloadPackage paths
    (creTrummer.rig.defVariant, creTrummer.mod.defVariant), and usdSublayer paths
    (shd.defVariant.100_defSublayer).
    
    Args:
        payloadPath: Full path to payload package or sublayer.
        
    Returns:
        Department name or None.
    """
    pathLower = payloadPath.lower()
    
    if '/geometry/' in pathLower or '.mod.' in pathLower:
        return 'Model'
    elif '/texturebundle' in pathLower or '.tex.' in pathLower:
        return 'Texture'
    elif '/precomp/' in pathLower or '/shading/' in pathLower or '.shd.' in pathLower or '/usdsublayer/' in pathLower:
        return 'Shading'
    elif '/rig/' in pathLower or '.rig.' in pathLower:
        return 'Rig'
    elif '/groom/' in pathLower or '/hair/' in pathLower or '.hair.' in pathLower:
        return 'Groom'
    
    return None


def parseLayerStackReferences(layerStackPath):
    """Parse layer stack to extract referenced Payload Package versions per department.
    
    Scans the layers/ subdirectory for department-specific layer files and
    extracts the Payload Package version each layer references (not the LayerStack version).
    
    Args:
        layerStackPath: Path to layer stack version directory (e.g., .../v11).
        
    Returns:
        Dict mapping department to referenced Payload Package version number.
    """
    results = {
        'Model': None,
        'Texture': None,
        'Shading': None,
        'Rig': None,
        'Groom': None
    }
    
    if not os.path.exists(layerStackPath):
        return results
    
    try:
        versionMatch = re.search(r'/v(\d+)$', layerStackPath)
        if not versionMatch:
            print(f"[DEBUG] Could not extract version from path: {layerStackPath}")
            return results
        
        layerStackVersion = int(versionMatch.group(1))
        
        layersDir = os.path.join(layerStackPath, 'expanded', 'layers')
        if not os.path.exists(layersDir):
            print(f"[DEBUG] Layers directory not found: {layersDir}")
            return results
        
        print(f"[DEBUG] Scanning LayerStack v{layerStackVersion} layers: {layersDir}")
        
        deptPatterns = {
            'Model': ['.mod.', 'model'],
            'Texture': ['.tex.', 'texture'],
            'Shading': ['.shd.', 'shading'],
            'Rig': ['.rig.', 'rigging'],
            'Groom': ['.grm.', 'groom', 'hair']
        }
        
        for fileName in os.listdir(layersDir):
            if not (fileName.endswith('.usd') or fileName.endswith('.usda')):
                continue
            
            fileNameLower = fileName.lower()
            for dept, patterns in deptPatterns.items():
                if any(pattern in fileNameLower for pattern in patterns):
                    filePath = os.path.join(layersDir, fileName)
                    referencedVersion = extractReferencedVersionFromLayer(filePath)
                    
                    if referencedVersion:
                        results[dept] = referencedVersion
                        print(f"[DEBUG] {dept} layer references Payload Package v{referencedVersion}")
                    else:
                        print(f"[DEBUG] Could not extract referenced version from {fileName}")
                    break
        
        return results
        
    except Exception as error:
        print(f"[ERROR] Failed to parse layer stack references: {error}")
        import traceback
        traceback.print_exc()
        return results


def extractReferencedVersionFromLayer(layerFilePath):
    """Extract the Payload Package version referenced by a layer file.
    
    Reads the binary USD file using strings and extracts version='vN' pattern.
    
    Args:
        layerFilePath: Path to layer USD file.
        
    Returns:
        Version number (int) or None.
    """
    try:
        with open(layerFilePath, 'rb') as fileHandle:
            content = fileHandle.read()
        
        contentStr = content.decode('latin-1', errors='ignore')
        
        versionMatch = re.search(r"version=['\"]v(\d+)['\"]", contentStr)
        if versionMatch:
            return int(versionMatch.group(1))
        
        versionMatch = re.search(r'\.v(\d+)\.usd', contentStr)
        if versionMatch:
            return int(versionMatch.group(1))
        
        versionMatch = re.search(r'/v(\d+)/', contentStr)
        if versionMatch:
            return int(versionMatch.group(1))
        
        allVersions = re.findall(r'v(\d+)', contentStr)
        if allVersions:
            versions = [int(v) for v in allVersions]
            maxVersion = max(versions)
            print(f"[DEBUG] Found versions {versions} in layer, using max: v{maxVersion}")
            return maxVersion
        
        return None
        
    except Exception as error:
        print(f"[ERROR] Failed to extract version from {layerFilePath}: {error}")
        return None


def detectMismatches(dept, shotgridData, payloadData, layerStackData):
    """Detect version mismatches for a department.
    
    Args:
        dept: Department name.
        shotgridData: Dict with ShotGrid version info.
        payloadData: Dict with payload package version info.
        layerStackData: Dict with layer stack version info.
        
    Returns:
        List of mismatch dicts.
    """
    mismatches = []
    
    sgVersion = shotgridData.get('version') if shotgridData else None
    ppVersion = payloadData.get('version') if payloadData else None
    lsVersion = layerStackData
    
    if sgVersion is None:
        return mismatches
    
    if ppVersion is None:
        mismatches.append(buildMismatchItem(
            'PP_NOT_BUILT',
            f'ShotGrid has approved v{sgVersion} but no Payload Package exists',
            'error',
            suggestionText=f'buildPayloadPackage -s {DEPT_TO_STEP_MAP.get(dept, dept.lower())} -p',
            confluenceLink=CONFLUENCE_LINKS.get('PP_NOT_BUILT')
        ))
        return mismatches
    
    if sgVersion > ppVersion:
        ppPath = payloadData.get('path')
        if ppPath:
            validation = payload_parser.validatePayloadContent(dept, sgVersion, ppVersion, ppPath)
            
            if validation['contentMatch']:
                refVersions = ', '.join([f"v{v}" for v in validation['referencedVersions']])
                mismatches.append(buildMismatchItem(
                    'VERSION_MISMATCH_CONTENT_OK',
                    f'SG v{sgVersion} > PP v{ppVersion}, but content identical (references {refVersions})',
                    'info',
                    suggestionText='No rebuild needed - content already matches',
                    confluenceLink=CONFLUENCE_LINKS.get('VERSION_MISMATCH')
                ))
            elif validation['needsRebuild'] and validation['referencedVersions']:
                refVersions = ', '.join([f"v{v}" for v in validation['referencedVersions']])
                mismatches.append(buildMismatchItem(
                    'VERSION_MISMATCH_CONTENT_STALE',
                    f'SG v{sgVersion} but PP v{ppVersion} references {refVersions} - content is stale',
                    'warning',
                    suggestionText=f'buildPayloadPackage -s {DEPT_TO_STEP_MAP.get(dept, dept.lower())} -p',
                    confluenceLink=CONFLUENCE_LINKS.get('VERSION_MISMATCH')
                ))
            else:
                mismatches.append(buildMismatchItem(
                    'VERSION_MISMATCH',
                    f'SG v{sgVersion} but PP v{ppVersion} (content validation unavailable)',
                    'info',
                    suggestionText=f'buildPayloadPackage -s {DEPT_TO_STEP_MAP.get(dept, dept.lower())} -p # will skip if content unchanged',
                    confluenceLink=CONFLUENCE_LINKS.get('VERSION_MISMATCH')
                ))
        else:
            mismatches.append(buildMismatchItem(
                'VERSION_MISMATCH',
                f'SG v{sgVersion} but PP v{ppVersion} (may be OK if content identical)',
                'info',
                suggestionText=f'buildPayloadPackage -s {DEPT_TO_STEP_MAP.get(dept, dept.lower())} -p # will skip if content unchanged',
                confluenceLink=CONFLUENCE_LINKS.get('VERSION_MISMATCH')
            ))
    
    if lsVersion is not None and ppVersion != lsVersion:
        mismatches.append(buildMismatchItem(
            'LAYERSTACK_STALE',
            f'Payload Package v{ppVersion} but Layer Stack references v{lsVersion}',
            'warning',
            suggestionText='buildLayerStack -p # rebuilds LayerStack to reference current Payload Packages',
            confluenceLink=CONFLUENCE_LINKS.get('LAYERSTACK_STALE')
        ))
    
    return mismatches


def checkFileExistence(payloadData):
    """Check if payload package file exists on disk.
    
    Args:
        payloadData: Dict with path field.
        
    Returns:
        Boolean indicating existence.
    """
    if not payloadData:
        return False
    
    path = payloadData.get('path')
    if not path:
        return False
    
    return os.path.exists(path)


def aggregateFixCommands(departments):
    """Aggregate fix commands in correct execution order.
    
    Args:
        departments: Dict of department analysis results.
        
    Returns:
        List of fix command strings.
    """
    ppCommands = []
    needsLayerStackRebuild = False
    
    for dept, data in departments.items():
        mismatches = data.get('mismatches', [])
        for mismatch in mismatches:
            if mismatch['type'] in ['VERSION_MISMATCH', 'PP_NOT_BUILT']:
                step = DEPT_TO_STEP_MAP.get(dept, dept.lower())
                cmd = f'buildPayloadPackage -s {step} -p'
                if cmd not in ppCommands:
                    ppCommands.append(cmd)
            elif mismatch['type'] == 'LAYERSTACK_STALE':
                needsLayerStackRebuild = True
    
    fixCommands = ppCommands
    if needsLayerStackRebuild:
        fixCommands.append('buildLayerStack -p')
    
    return fixCommands


def checkRigTopology(sgConnection, assetId, assetCode, showCode, modelData, rigData):
    """Check if rig needs rebuilding due to model topology changes.
    
    Uses the same logic as Show Monitor audit (Phase 2 UV hash comparison).
    
    Args:
        sgConnection: ShotGrid API connection.
        assetId: Asset entity ID.
        assetCode: Asset code string.
        showCode: Show/project tank name.
        modelData: ShotGrid resolver result for Model department.
        rigData: ShotGrid resolver result for Rig department.
        
    Returns:
        Mismatch dict or None.
    """
    if not modelData or not rigData:
        return None
    
    if modelData.get('dept_status') != 'available' or rigData.get('dept_status') != 'available':
        return None
    
    modelPub = modelData.get('publish', {})
    rigPub = rigData.get('publish', {})
    modelDate = modelPub.get('created_at', '')
    rigDate = rigPub.get('created_at', '')
    
    if not (modelDate and rigDate and modelDate > rigDate):
        return None
    
    modelVersion = modelData.get('version', 0)
    rigVersion = rigData.get('version', 0)
    
    modelPublishes = asset_checks.queryModelPublishes(sgConnection, assetId)
    rigModelVersion = geometry_hash_utils.findModelVersionAtRigDate(modelPublishes, rigDate)
    
    if rigModelVersion is None:
        rigModelVersion = 1
    
    if rigModelVersion >= modelVersion:
        return None
    
    hashResult = geometry_hash_utils.detectChangesSinceVersion(
        showCode, assetCode, rigModelVersion
    )
    
    if hashResult.get("noGeodata"):
        return {
            'type': 'RIG_OUTDATED_NO_GEODATA',
            'severity': 'warning',
            'message': f'Model v{modelVersion} published after Rig v{rigVersion} - Rig may need updating (no geodata to verify topology)',
            'suggestion': f'# Check if rig needs rebuilding\n# Model: v{rigModelVersion} → v{modelVersion}\n# Rig: v{rigVersion}'
        }
    
    if hashResult["topologyChanged"]:
        changedDetails = [d for d in hashResult["details"] if d["topologyChanged"]]
        detailStr = ""
        if changedDetails:
            firstChange = changedDetails[0]
            variantShort = firstChange["variant"].split(".")[-1]
            detailStr = f" ({variantShort} v{firstChange['versionA']}→v{firstChange['versionB']})"
        
        return {
            'type': 'RIG_OUTDATED_TOPOLOGY',
            'severity': 'error',
            'message': f'Model topology changed since Rig v{rigVersion} was built (model v{rigModelVersion}→v{modelVersion}){detailStr}',
            'suggestion': f'# Rebuild rig to match new model topology\n# Model changed: v{rigModelVersion} → v{modelVersion}\n# Current rig: v{rigVersion}',
            'confluenceLink': 'https://confluence.rodeofx.com/display/PIPELINE/Rigging+Pipeline'
        }
    
    if hashResult["uvChanged"]:
        return {
            'type': 'RIG_OK_UV_ONLY',
            'severity': 'info',
            'message': f'Model v{rigModelVersion}→v{modelVersion}: only UV changed, Rig v{rigVersion} does not need updating',
            'suggestion': None
        }
    
    return None


def analyzeAssetPipeline(sgConnection, assetCode, showCode=None, includePolicyChecks=True):
    """Analyze asset pipeline across ShotGrid, Payload Package, and Layer Stack.
    
    Main entry point for asset analyzer.
    
    Args:
        sgConnection: ShotGrid API connection.
        assetCode: Asset code (e.g., 'chrNolmen').
        showCode: Optional show code. If None, queries from asset.
        includePolicyChecks: Whether to include shared policy checks in mismatch output.
        
    Returns:
        Dict with comprehensive analysis results.
    """
    print(f"[DEBUG] analyzeAssetPipeline called with assetCode={assetCode}, showCode={showCode}")
    asset = queryAssetByCode(sgConnection, assetCode, showCode)
    if not asset:
        return {
            'error': f'Asset not found: {assetCode} in show {showCode}',
            'assetCode': assetCode,
            'departments': {},
            'globalIssues': [],
            'summary': {'totalDepartments': 0, 'matchCount': 0, 'mismatchCount': 0}
        }
    
    assetId = asset.get('id')
    assetShowCode = extractShowCode(asset)
    print(f"[DEBUG] Found asset ID={assetId}, asset's show={assetShowCode}, requested show={showCode}")
    
    if not showCode:
        showCode = assetShowCode
    
    if not showCode:
        return {
            'error': 'Could not determine show code from asset',
            'assetCode': assetCode,
            'assetId': assetId,
            'departments': {},
            'globalIssues': [],
            'summary': {'totalDepartments': 0, 'matchCount': 0, 'mismatchCount': 0}
        }
    
    print(f"[DEBUG] Analyzing asset: {assetCode} (ID: {assetId}, Show: {showCode})")
    
    try:
        shotgridResults = asset_resolver.resolveLatestPerDept(sgConnection, assetId)
    except Exception as error:
        print(f"[ERROR] ShotGrid query failed: {error}")
        shotgridResults = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        ppFuture = executor.submit(payload_parser.parsePayloadVersions, sgConnection, assetCode, showCode)
        lsFuture = executor.submit(findLayerStackForAsset, showCode, assetCode)
        
        try:
            payloadResults = ppFuture.result()
        except Exception as error:
            print(f"[ERROR] Payload parsing failed: {error}")
            payloadResults = payload_parser.buildEmptyPayloadResults()
        
        try:
            layerStackInfo = lsFuture.result()
        except Exception as error:
            print(f"[ERROR] LayerStack lookup failed: {error}")
            layerStackInfo = None
    
    layerStackVersions = {}
    if layerStackInfo:
        layerStackVersions = parseLayerStackReferences(layerStackInfo['path'])
        print(f"[DEBUG] Layer Stack v{layerStackInfo['version']}: {layerStackVersions}")
    else:
        print(f"[DEBUG] No Layer Stack found for {assetCode}")
    
    departments = {}
    matchCount = 0
    mismatchCount = 0
    
    for dept in DEPARTMENTS:
        sgData = shotgridResults.get(dept.lower())
        ppData = payloadResults.get(dept)
        lsVersion = layerStackVersions.get(dept)
        
        sgVersion = None
        sgStatus = None
        sgDate = None
        sgPublishId = None
        if sgData and sgData.get('dept_status') == 'available':
            sgVersion = sgData.get('version')
            pub = sgData.get('publish')
            if pub:
                sgStatus = pub.get('sg_status_list')
                sgDate = pub.get('created_at')
                sgPublishId = pub.get('id')
        
        ppVersion = ppData.get('version') if ppData else None
        ppPath = ppData.get('path') if ppData else None
        ppDate = ppData.get('date') if ppData else None
        ppStatus = ppData.get('status') if ppData else None
        ppExists = checkFileExistence(ppData) if ppData else False
        
        mismatches = detectMismatches(
            dept,
            {'version': sgVersion, 'status': sgStatus} if sgVersion else None,
            ppData,
            lsVersion
        )
        
        if mismatches:
            mismatchCount += 1
        else:
            matchCount += 1
        
        departments[dept] = {
            'shotgrid': {
                'latestApproved': f'v{sgVersion}' if sgVersion else None,
                'status': sgStatus,
                'date': sgDate,
                'publishId': sgPublishId
            },
            'payloadPackage': {
                'version': f'v{ppVersion}' if ppVersion else None,
                'path': ppPath,
                'date': ppDate,
                'status': ppStatus,
                'exists': ppExists
            },
            'layerStack': {
                'referencedPayloadPackageVersion': f'v{lsVersion}' if lsVersion else None,
                'path': layerStackInfo.get('path') if layerStackInfo else None
            },
            'mismatches': mismatches
        }
    
    policyIssues = []
    if includePolicyChecks:
        policyIssues = asset_checks.checkAssetIssues(
            sgConnection,
            {'id': assetId, 'code': assetCode},
            {},
            showCode=showCode,
            resolverResults=shotgridResults,
        )
        for policyIssue in policyIssues:
            targetDepartment = getPolicyDepartment(policyIssue)
            if targetDepartment not in departments:
                continue
            departments[targetDepartment]['mismatches'].append(
                convertPolicyIssueToAnalyzerMismatch(policyIssue)
            )

    mismatchCount = sum(
        1 for departmentData in departments.values() if departmentData.get('mismatches')
    )
    matchCount = len(DEPARTMENTS) - mismatchCount
    
    globalIssues = []
    if layerStackInfo:
        staleDepts = sum(1 for d in departments.values() if any(m['type'] == 'LAYERSTACK_STALE' for m in d['mismatches']))
        if staleDepts > 0:
            globalIssues.append({
                'type': 'LAYERSTACK_STALE',
                'message': f'Layer Stack v{layerStackInfo["version"]} references outdated versions. {staleDepts} department(s) have newer Payload Packages.'
            })
    
    fixCommands = aggregateFixCommands(departments)
    
    return {
        'assetCode': assetCode,
        'assetId': assetId,
        'showCode': showCode,
        'layerStackVersion': layerStackInfo.get('version') if layerStackInfo else None,
        'policyIssues': policyIssues,
        'ruleCatalogVersion': asset_checks.RULE_CATALOG_VERSION,
        'departments': departments,
        'globalIssues': globalIssues,
        'fixCommands': fixCommands,
        'summary': {
            'totalDepartments': len(DEPARTMENTS),
            'matchCount': matchCount,
            'mismatchCount': mismatchCount,
            'missingFileCount': sum(1 for d in departments.values() if not d['payloadPackage']['exists'])
        }
    }
