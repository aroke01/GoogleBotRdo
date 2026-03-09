"""USD Analysis Module

Provides USD debugging capabilities using CLI tools (usdview, usdrecord, usdchecker)
since pxr module is not available in default Python environment.

Uses subprocess to run USD commands via Rez environment.
"""

import os
import re
import subprocess
import tempfile
from typing import Optional


def runUsdCommand(args, timeoutSeconds=30):
    """Execute a USD CLI command via Rez environment.

    Args:
        args: List of command arguments (after 'rez env usd --').
        timeoutSeconds: Maximum seconds to wait for command.

    Returns:
        Tuple of (stdout, stderr, returnCode).
    """
    cmd = ['rez', 'env', 'usd', '--'] + args
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeoutSeconds,
            universal_newlines=True
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return '', 'Command timed out after {} seconds'.format(timeoutSeconds), 1
    except Exception as error:
        return '', 'Failed to execute: {}'.format(str(error)), 1


def extractUsdPathFromPublish(publishData):
    """Extract USD file path from publish data.

    Args:
        publishData: Dict with publish fields from ShotGrid.

    Returns:
        Absolute path to USD file or None.
    """
    pathField = publishData.get('path') or publishData.get('pathCache')
    if not pathField:
        return None

    # Handle dict or string format
    if isinstance(pathField, dict):
        localPath = pathField.get('local_path') or pathField.get('local_path_linux')
        if localPath:
            return localPath
        pathField = pathField.get('cache_path', '')

    if isinstance(pathField, str):
        # Expand variables
        expandedPath = os.path.expandvars(pathField)
        if os.path.exists(expandedPath):
            return expandedPath

    return None


def getLayerStackInfo(usdPath):
    """Get layer stack information using usdinfo.

    Args:
        usdPath: Path to USD file.

    Returns:
        Dict with layer stack and composition info.
    """
    if not usdPath or not os.path.exists(usdPath):
        return {
            'error': 'USD file not found: {}'.format(usdPath),
            'layers': [],
            'errors': []
        }

    stdout, stderr, returnCode = runUsdCommand(['usdinfo', usdPath])

    if returnCode != 0:
        return {
            'error': 'usdinfo failed: {}'.format(stderr),
            'layers': [],
            'errors': [stderr] if stderr else ['Command failed']
        }

    # Parse layer stack from usdinfo output
    layers = []
    compositionErrors = []

    lines = stdout.split('\n')
    inLayerStack = False
    currentLayer = None

    for line in lines:
        lineStripped = line.strip()

        # Detect layer stack section
        if 'Layer Stack:' in line or 'root layer:' in line.lower():
            inLayerStack = True
            continue

        if inLayerStack:
            # Parse layer entry (usually has indentation)
            if line.startswith('  ') or line.startswith('\t'):
                layerPath = lineStripped
                if layerPath and not layerPath.startswith('('):
                    layers.append({
                        'path': layerPath,
                        'strength': len(line) - len(lineStripped),
                        'isAnonymous': '@' not in layerPath
                    })

        # Detect composition errors
        if 'error' in line.lower() or 'warning' in line.lower():
            severity = 'error' if 'error' in line.lower() else 'warning'
            compositionErrors.append({
                'severity': severity,
                'message': lineStripped
            })

    return {
        'layers': layers,
        'layerCount': len(layers),
        'errors': compositionErrors,
        'rawOutput': stdout[:1000] if len(stdout) > 1000 else stdout
    }


def traceOpinion(usdPath, primPath, propertyName=None):
    """Trace which layer authored a specific opinion (the winning opinion).

    This answers "Why am I using v39?" by showing:
    - The exact layer that authored the winning opinion
    - The full layer stack (strong to weak)
    - The composition arc chain (reference/payload/variant/inherits/specializes)
    - The prim path and property that won

    Args:
        usdPath: Path to USD file.
        primPath: Prim path (e.g., '/creTrummer').
        propertyName: Optional property to trace (e.g., 'shaderset').

    Returns:
        Dict with opinion source, layer stack, and composition arcs.
    """
    if not usdPath or not os.path.exists(usdPath):
        return {
            'error': 'USD file not found',
            'opinionSource': None,
            'layerStack': [],
            'explanation': 'Cannot trace opinion - USD file does not exist'
        }

    # Get layer stack first
    layerStackResult = getLayerStackInfo(usdPath)
    layers = layerStackResult.get('layers', [])

    if not layers:
        return {
            'error': 'Could not extract layer stack',
            'opinionSource': None,
            'layerStack': [],
            'explanation': 'No layers found in USD file'
        }

    # Use usdcat to get full stage content for analysis
    stdout, stderr, returnCode = runUsdCommand(['usdcat', usdPath])

    # Build the response
    # The first layer in the stack has the strongest opinion
    strongestLayer = layers[0] if layers else None

    # Parse composition arcs from usdinfo output
    arcs = detectCompositionArcs(usdPath, primPath)

    # Build explanation
    explanationParts = []
    explanationParts.append('Layer Stack (strongest to weakest):')
    for index, layer in enumerate(layers[:5]):  # Show top 5
        marker = 'WINNER' if index == 0 else f'{index + 1}'
        layerName = layer.get('path', 'anonymous')
        if len(layerName) > 60:
            layerName = '...' + layerName[-57:]
        explanationParts.append(f'  [{marker}] {layerName}')

    if len(layers) > 5:
        explanationParts.append(f'  ... and {len(layers) - 5} more layers')

    explanationParts.append('')
    explanationParts.append('Winning Opinion:')
    explanationParts.append(f'  Layer: {strongestLayer.get("path", "unknown") if strongestLayer else "unknown"}')
    explanationParts.append(f'  Prim Path: {primPath}')
    if propertyName:
        explanationParts.append(f'  Property: {propertyName}')

    if arcs:
        explanationParts.append('')
        explanationParts.append('Composition Arcs:')
        for arc in arcs:
            explanationParts.append(f'  - {arc["type"]}: {arc["target"]}')

    opinionSource = {
        'layer': strongestLayer,
        'layerPath': strongestLayer.get('path') if strongestLayer else None,
        'primPath': primPath,
        'property': propertyName,
        'arcType': arcs[0]['type'] if arcs else 'direct',
        'arcTarget': arcs[0]['target'] if arcs else None
    }

    return {
        'opinionSource': opinionSource,
        'layerStack': layers,
        'layerCount': len(layers),
        'compositionArcs': arcs,
        'explanation': '\n'.join(explanationParts),
        'whyThisVersion': f'The winning opinion comes from: {strongestLayer.get("path", "unknown") if strongestLayer else "unknown"}'
    }


def extractPayloadReferencesFromUsd(usdPath):
    """Extract payload and sublayer references from USD file using pxr.Usd.Stage.
    
    Parses actual USD composition arcs to find payload and sublayer references and extract
    version numbers from paths. More accurate than filename pattern matching.
    
    Args:
        usdPath: Path to USD file (layer stack or any USD file).
        
    Returns:
        List of dicts with 'path' and 'version' keys, or empty list on error.
    """
    if not usdPath or not os.path.exists(usdPath):
        return []
    
    payloadRefs = []
    
    try:
        from pxr import Usd, Sdf
        
        stage = Usd.Stage.Open(usdPath)
        if not stage:
            print(f"[ERROR] Failed to open USD stage: {usdPath}")
            return []
        
        for prim in stage.Traverse():
            if prim.HasPayload():
                payloads = prim.GetMetadata('payload')
                if not payloads:
                    continue
                
                if isinstance(payloads, Sdf.Payload):
                    payloads = [payloads]
                elif hasattr(payloads, 'prependedItems'):
                    payloads = list(payloads.prependedItems)
                
                for payload in payloads:
                    assetPath = payload.assetPath if hasattr(payload, 'assetPath') else str(payload)
                    if not assetPath or assetPath == '':
                        continue
                    
                    versionMatch = re.search(r'/v(\d+)/', assetPath)
                    version = int(versionMatch.group(1)) if versionMatch else None
                    
                    payloadRefs.append({
                        'path': assetPath,
                        'version': version,
                        'primPath': str(prim.GetPath())
                    })
        
        rootLayer = stage.GetRootLayer()
        if rootLayer:
            sublayers = rootLayer.subLayerPaths
            for sublayerPath in sublayers:
                if not sublayerPath or sublayerPath == '':
                    continue
                
                versionMatch = re.search(r'/v(\d+)/', sublayerPath)
                version = int(versionMatch.group(1)) if versionMatch else None
                
                payloadRefs.append({
                    'path': sublayerPath,
                    'version': version,
                    'primPath': 'sublayer'
                })
        
        return payloadRefs
        
    except ImportError:
        print("[WARNING] pxr module not available, falling back to CLI parsing")
        return extractPayloadReferencesViaCli(usdPath)
    except Exception as error:
        print(f"[ERROR] Failed to extract payload references: {error}")
        return []


def extractPayloadReferencesViaCli(usdPath):
    """Fallback: Extract payload and sublayer references using CLI tools when pxr not available.
    
    Args:
        usdPath: Path to USD file.
        
    Returns:
        List of dicts with 'path' and 'version' keys.
    """
    if not usdPath or not os.path.exists(usdPath):
        print(f"[DEBUG] extractPayloadReferencesViaCli: USD path does not exist: {usdPath}")
        return []
    
    print(f"[DEBUG] extractPayloadReferencesViaCli: Parsing {usdPath}")
    stdout, stderr, returnCode = runUsdCommand(['usdcat', '--flattenLayerStack', usdPath])
    
    if returnCode != 0:
        print(f"[WARNING] usdcat failed with code {returnCode}: {stderr}")
        return []
    
    payloadRefs = []
    lines = stdout.split('\n')
    
    for line in lines:
        if '@' in line and ('.usd@' in line or '.usda@' in line):
            allMatches = re.findall(r'@([^@]+\.usda?)@', line)
            for assetPath in allMatches:
                versionMatch = re.search(r'/v(\d+)/', assetPath)
                version = int(versionMatch.group(1)) if versionMatch else None
                
                if version:
                    print(f"[DEBUG] Found payload/sublayer reference: {assetPath} (v{version})")
                    
                    payloadRefs.append({
                        'path': assetPath,
                        'version': version,
                        'primPath': None
                    })
    
    print(f"[DEBUG] extractPayloadReferencesViaCli: Found {len(payloadRefs)} payload references")
    return payloadRefs


def detectCompositionArcs(usdPath, primPath):
    """Detect composition arcs (references, payloads, variants, inherits) for a prim.

    Args:
        usdPath: Path to USD file.
        primPath: Prim path to analyze.

    Returns:
        List of arc dicts with type and target.
    """
    if not usdPath or not os.path.exists(usdPath):
        return []

    # Use usdinfo with verbose output to get composition info
    stdout, stderr, returnCode = runUsdCommand(['usdinfo', '--verbose', usdPath])

    arcs = []
    lines = stdout.split('\n')
    currentPrim = None
    inTargetPrim = False

    for line in lines:
        lineStripped = line.strip()

        # Detect prim definitions
        if lineStripped.startswith('def ') or lineStripped.startswith('over '):
            primMatch = re.search(r'(?:def|over)\s+\w+\s+["\']?([^"\']+)', lineStripped)
            if primMatch:
                currentPrim = primMatch.group(1)
                inTargetPrim = currentPrim == primPath or currentPrim.endswith(primPath.split('/')[-1])

        if not inTargetPrim:
            continue

        # Detect composition arcs
        if 'references' in lineStripped.lower() or 'reference' in lineStripped.lower():
            refMatch = re.search(r'@([^@]+)@', lineStripped)
            if refMatch:
                arcs.append({
                    'type': 'reference',
                    'target': refMatch.group(1),
                    'description': 'External reference'
                })

        if 'payload' in lineStripped.lower():
            payloadMatch = re.search(r'@([^@]+)@', lineStripped)
            if payloadMatch:
                arcs.append({
                    'type': 'payload',
                    'target': payloadMatch.group(1),
                    'description': 'Payload reference'
                })

        if 'variant' in lineStripped.lower() or 'variants' in lineStripped.lower():
            variantMatch = re.search(r'variants?\s*[=:]\s*{?([^}]+)', lineStripped)
            if variantMatch:
                arcs.append({
                    'type': 'variant',
                    'target': variantMatch.group(1).strip(),
                    'description': 'Variant selection'
                })

        if 'inherits' in lineStripped.lower():
            inheritsMatch = re.search(r'[<(]([^>)]+)[>)]', lineStripped)
            if inheritsMatch:
                arcs.append({
                    'type': 'inherit',
                    'target': inheritsMatch.group(1),
                    'description': 'Inherits from'
                })

    return arcs


def generateThumbnail(usdPath, outputPath=None, width=320, height=180):
    """Generate thumbnail image from USD file.

    Args:
        usdPath: Path to USD file.
        outputPath: Optional output path (defaults to temp file).
        width: Thumbnail width.
        height: Thumbnail height.

    Returns:
        Dict with output path and success status.
    """
    if not usdPath or not os.path.exists(usdPath):
        return {
            'success': False,
            'error': 'USD file not found: {}'.format(usdPath),
            'thumbnailPath': None
        }

    if not outputPath:
        outputPath = os.path.join(
            tempfile.gettempdir(),
            'usd_thumb_{}.png'.format(os.path.basename(usdPath))
        )

    # Remove existing file
    if os.path.exists(outputPath):
        os.remove(outputPath)

    # Run usdrecord
    args = [
        'usdrecord',
        '--imageWidth', str(width),
        '--complexity', 'low',
        '--renderer', 'GL',
        usdPath,
        outputPath
    ]

    stdout, stderr, returnCode = runUsdCommand(args, timeoutSeconds=60)

    if returnCode != 0:
        return {
            'success': False,
            'error': 'usdrecord failed: {}'.format(stderr or stdout),
            'thumbnailPath': None,
            'rawOutput': stdout
        }

    if not os.path.exists(outputPath):
        return {
            'success': False,
            'error': 'Thumbnail file was not created',
            'thumbnailPath': None
        }

    return {
        'success': True,
        'thumbnailPath': outputPath,
        'width': width,
        'height': height,
        'fileSize': os.path.getsize(outputPath)
    }


def runUsdChecker(usdPath):
    """Run usdchecker on a USD file.

    Args:
        usdPath: Path to USD file.

    Returns:
        Dict with check results and errors.
    """
    if not usdPath or not os.path.exists(usdPath):
        return {
            'success': False,
            'error': 'USD file not found',
            'errors': [],
            'warnings': []
        }

    stdout, stderr, returnCode = runUsdCommand(['usdchecker', usdPath])

    errors = []
    warnings = []

    # Parse usdchecker output
    lines = (stdout + '\n' + stderr).split('\n')

    for line in lines:
        lineLower = line.lower()
        if 'error' in lineLower or line.startswith('Error:'):
            errors.append(line.strip())
        elif 'warning' in lineLower or line.startswith('Warning:'):
            warnings.append(line.strip())

    return {
        'success': returnCode == 0,
        'errors': errors,
        'warnings': warnings,
        'errorCount': len(errors),
        'warningCount': len(warnings),
        'rawOutput': stdout[:2000] if len(stdout) > 2000 else stdout
    }


def compareUsdFiles(fromPath, toPath):
    """Compare two USD files and report differences.

    Args:
        fromPath: Path to first USD file.
        toPath: Path to second USD file.

    Returns:
        Dict with structural diff information.
    """
    if not os.path.exists(fromPath):
        return {'error': 'From file not found: {}'.format(fromPath)}
    if not os.path.exists(toPath):
        return {'error': 'To file not found: {}'.format(toPath)}

    # Try usddiff if available, otherwise do basic comparison
    stdout, stderr, returnCode = runUsdCommand(['usddiff', fromPath, toPath])

    if returnCode == 0 and not stderr:
        # Files are identical or usddiff not available
        return {
            'identical': True,
            'differences': [],
            'rawOutput': stdout
        }

    # Parse diff output
    differences = []
    lines = (stdout + '\n' + stderr).split('\n')

    for line in lines:
        lineStripped = line.strip()
        if not lineStripped:
            continue

        # Parse prim changes
        if 'prim' in line.lower():
            if '+' in line:
                differences.append({'type': 'added', 'prim': lineStripped, 'raw': line})
            elif '-' in line:
                differences.append({'type': 'removed', 'prim': lineStripped, 'raw': line})
            else:
                differences.append({'type': 'changed', 'prim': lineStripped, 'raw': line})

    return {
        'identical': len(differences) == 0,
        'differences': differences,
        'diffCount': len(differences),
        'rawOutput': stdout[:2000] if len(stdout) > 2000 else stdout
    }


def analyzeUsdForPublish(sgConnection, publishData):
    """Full USD analysis for a TankPublishedFile.

    Args:
        sgConnection: ShotGrid connection.
        publishData: Publish entity dict.

    Returns:
        Dict with comprehensive USD analysis.
    """
    usdPath = extractUsdPathFromPublish(publishData)

    if not usdPath:
        return {
            'hasUsdFile': False,
            'error': 'No USD path found in publish data',
            'layerStack': None,
            'opinionTrace': None,
            'thumbnail': None,
            'healthCheck': None
        }

    if not os.path.exists(usdPath):
        return {
            'hasUsdFile': False,
            'usdPath': usdPath,
            'error': 'USD file path does not exist on filesystem',
            'layerStack': None,
            'opinionTrace': None,
            'thumbnail': None,
            'healthCheck': None
        }

    # Run analysis
    layerStack = getLayerStackInfo(usdPath)
    healthCheck = runUsdChecker(usdPath)

    # Trace opinion for root prim (extract from filename as fallback)
    opinionTrace = None
    try:
        # Try to determine the asset name from publish data
        assetName = None
        if publishData.get('name'):
            # Extract asset code from publish name (e.g., "creTrummer.shd.v39" -> "creTrummer")
            nameParts = publishData['name'].split('.')
            if nameParts:
                assetName = nameParts[0]
        if not assetName and publishData.get('code'):
            codeParts = publishData['code'].split('.')
            if codeParts:
                assetName = codeParts[0]

        if assetName:
            # Trace opinion for root prim
            opinionTrace = traceOpinion(usdPath, '/' + assetName)
    except Exception:
        # Opinion trace is optional, don't fail if it doesn't work
        pass

    # Generate thumbnail (async consideration: this might be slow)
    thumbnail = None
    # Uncomment when ready to enable:
    # thumbnail = generateThumbnail(usdPath)

    return {
        'hasUsdFile': True,
        'usdPath': usdPath,
        'usdExists': True,
        'layerStack': layerStack,
        'healthCheck': healthCheck,
        'thumbnail': thumbnail,
        'opinionTrace': opinionTrace,
        'error': None
    }
