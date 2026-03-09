"""
Asset Dailies Analysis Module

Analyzes asset publishes to track version progression across departments:
Model, Texture, Shading, Rig, Groom, Character FX.
"""

import sys
import os

pythonRoot = os.path.dirname(os.path.abspath(__file__))
if pythonRoot not in sys.path:
    sys.path.insert(0, pythonRoot)

import asset_resolver
from audits.asset_checks import checkAssetIssues
import payload_parser


ASSET_TANK_TYPES = {
    'Model': ['geometry', 'workfile'],
    'Texture': ['textureBundle2', 'textureBundle', 'texture'],
    'Shading': ['precomp', 'render', 'usdSublayer', 'workfile'],
    'Rig': ['rig', 'mocapRig', 'usdPayloadPackage', 'workfile', 'render'],
    'Groom': ['groom', 'yeti', 'workfile', 'workfileChunk'],
    'CFX': ['workfile', 'geometry.cache', 'deformedGeometry.cache']
}


ASSET_STEP_FILTERS = {
    'Model': 'Modeling',
    'Texture': 'Texturing',
    'Shading': 'Shading',
    'Rig': 'Rigging',
    'Groom': 'Hair',
    'CFX': 'Character FX'
}


def buildEmptyResults():
    """Build empty results structure for error cases.
    
    Returns:
        Dict with all categories set to None.
    """
    return {
        'Model': None,
        'Texture': None,
        'Shading': None,
        'Rig': None,
        'Groom': None,
        'CFX': None
    }


def extractAssetCodeFromPublish(publishName):
    """Extract asset code from publish name.
    
    Examples:
        creTrummer.hi.defVariant.body_v60 -> creTrummer
        tex.creTrummer.body.defVariant.full_v54 -> creTrummer
        
    Args:
        publishName: TankPublishedFile name field.
        
    Returns:
        Asset code string or None.
    """
    if not publishName:
        return None
    
    parts = publishName.split('.')
    
    assetPrefixes = ('cre', 'chr', 'char', 'prp', 'prop', 'env', 'veh', 'veg', 'dev', 'fx', 'lgt', 'cam', 'set')
    for part in parts:
        if part.lower().startswith(assetPrefixes):
            return part
    
    return None


def classifyPublishCategory(publish, step):
    """Classify which asset category a publish belongs to.
    
    Args:
        publish: TankPublishedFile entity dict.
        step: Step name (e.g., 'Modeling (A)', 'Texturing (A)').
        
    Returns:
        Category name ('Model', 'Texture', etc.) or None.
    """
    tankType = publish.get('tank_type', {})
    if isinstance(tankType, dict):
        tankType = tankType.get('name', '')
    
    publishName = publish.get('name', '')
    
    if not step:
        stepFromName = None
        if 'mod.' in publishName or '.hi.' in publishName or '.mi.' in publishName:
            stepFromName = 'Modeling'
        elif 'tex.' in publishName:
            stepFromName = 'Texturing'
        elif 'shd.' in publishName:
            stepFromName = 'Shading'
        elif 'rig.' in publishName or '.rig.' in publishName:
            stepFromName = 'Rigging'
        elif 'hair.' in publishName or 'groom' in publishName.lower():
            stepFromName = 'Hair'
        elif 'cfx.' in publishName or 'intermediate.' in publishName:
            stepFromName = 'Character'
        
        if not stepFromName:
            return None
        step = stepFromName
    
    if isinstance(step, dict):
        step = step.get('name', '')
    
    stepBase = step.split(' ')[0] if ' ' in step else step
    
    if stepBase == 'Modeling':
        if tankType in ASSET_TANK_TYPES['Model']:
            if 'mod.' in publishName or '.hi.' in publishName or '.mi.' in publishName or '.proxy.' in publishName:
                return 'Model'
    
    elif stepBase == 'Texturing':
        if tankType in ASSET_TANK_TYPES['Texture']:
            if 'tex.' in publishName:
                return 'Texture'
    
    elif stepBase == 'Shading':
        if tankType in ASSET_TANK_TYPES['Shading']:
            if 'shd.' in publishName:
                return 'Shading'
    
    elif stepBase == 'Rigging':
        if tankType in ASSET_TANK_TYPES['Rig']:
            if 'rig.' in publishName or '.rig.' in publishName:
                return 'Rig'
    
    elif stepBase == 'Hair':
        if tankType in ASSET_TANK_TYPES['Groom']:
            if 'hair.' in publishName or 'groom' in publishName.lower():
                return 'Groom'
    
    elif stepBase == 'Character':
        if tankType in ASSET_TANK_TYPES['CFX']:
            if 'cfx.' in publishName or 'intermediate.' in publishName:
                return 'CFX'
    
    return None


def analyzeAssetDailies(sgConnection, assetCode, maxRetries=3):
    """Query ShotGrid for asset publishes and organize by category.
    
    Uses unified asset_resolver for deterministic, fault-tolerant results.
    
    Args:
        sgConnection: ShotGrid API connection.
        assetCode: Asset code (e.g., 'creTrummer').
        maxRetries: Number of retry attempts for SG queries.
        
    Returns:
        Dict with categories as keys, each containing latest publish info.
        Never returns None - always returns structured result.
    """
    filters = [['code', 'is', assetCode]]
    fields = ['id']
    
    print("[DEBUG] Asset Dailies Query:")
    print("  Asset Code: {}".format(assetCode))
    
    for attempt in range(maxRetries):
        try:
            assets = sgConnection.find('Asset', filters, fields)
            if not assets:
                print("[ERROR] Asset '{}' not found".format(assetCode))
                return buildEmptyResults()
            
            assetId = assets[0].get('id')
            print("[DEBUG] Found asset ID: {}".format(assetId))
            break
        except Exception as error:
            if attempt == maxRetries - 1:
                print("[ERROR] Failed to query asset after {} attempts: {}".format(maxRetries, error))
                return buildEmptyResults()
            import time
            time.sleep(1 * (attempt + 1))
    
    resolverResults = asset_resolver.resolveLatestPerDept(sgConnection, assetId)
    
    results = {
        'Model': None,
        'Texture': None,
        'Shading': None,
        'Rig': None,
        'Groom': None,
        'CFX': None
    }
    
    deptMapping = {
        'model': 'Model',
        'texture': 'Texture',
        'shading': 'Shading',
        'rig': 'Rig',
        'groom': 'Groom'
    }
    
    for resolverDept, info in resolverResults.items():
        displayDept = deptMapping.get(resolverDept)
        if not displayDept:
            continue
        
        deptStatus = info.get('dept_status')
        
        if deptStatus == 'not_started':
            results[displayDept] = None
            print("[DEBUG] {}: Not started (no publishes)".format(displayDept))
            continue
        
        if deptStatus == 'missing':
            results[displayDept] = None
            print("[DEBUG] {}: Missing department (no real publishes, ignoring global_latest fallback)".format(displayDept))
            continue
        
        pub = info.get('publish')
        if not pub:
            results[displayDept] = None
            print("[DEBUG] {}: No publish data available".format(displayDept))
            continue
        
        results[displayDept] = {
            'id': pub.get('id'),
            'name': pub.get('name'),
            'code': pub.get('code'),
            'version': info.get('version'),
            'status': pub.get('sg_status_list'),
            'user': (pub.get('created_by') or {}).get('name', 'Unknown'),
            'date': pub.get('created_at'),
            'tankType': (pub.get('tank_type') or {}).get('name', 'Unknown'),
            'dept_status': deptStatus,
            'confidence': info.get('confidence'),
            'has_duplicates': info.get('has_duplicates', False)
        }
        
        print("[DEBUG] {}: v{} by {} (status: {}, confidence: {})".format(
            displayDept,
            info.get('version'),
            results[displayDept]['user'],
            deptStatus,
            info.get('confidence')
        ))
    
    asset = {'id': assetId, 'code': assetCode}
    issues = checkAssetIssues(sgConnection, asset, {})
    results['issues'] = issues
    results['asset_id'] = assetId
    
    print("[DEBUG] Found {} issues for {}".format(len(issues), assetCode))
    
    payloadVersions = payload_parser.parsePayloadVersions(sgConnection, assetCode)
    results['payload'] = payloadVersions
    print("[DEBUG] Payload versions: {}".format(payloadVersions))
    
    return results
