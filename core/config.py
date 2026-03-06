"""
Space configuration module for rdo_googlebot.

Manages persistent Space-to-Show mappings stored in spaces.json.
"""

import os
import json
import re
from datetime import datetime


def getConfigPath():
    """Get absolute path to spaces.json config file.
    
    Returns:
        str: Absolute path to spaces.json
    """
    projectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(projectRoot, 'spaces.json')


def loadSpaceConfig():
    """Load Space configuration from spaces.json.
    
    Returns:
        dict: Space configuration mapping Space IDs to show codes
            Format: {"SPACE_ID": {"show": "lbp3", "name": "...", "configured_at": "..."}}
    """
    configPath = getConfigPath()
    
    if not os.path.exists(configPath):
        return {}
    
    try:
        with open(configPath, 'r') as fileHandle:
            return json.load(fileHandle)
    except (json.JSONDecodeError, IOError):
        return {}


def saveSpaceConfig(config):
    """Save Space configuration to spaces.json.
    
    Args:
        config: Dictionary mapping Space IDs to show configs
    """
    configPath = getConfigPath()
    
    with open(configPath, 'w') as fileHandle:
        json.dump(config, fileHandle, indent=2)


def getSpaceIdFromWebhook(webhookUrl):
    """Extract Space ID from Google Chat webhook URL.
    
    Args:
        webhookUrl: Webhook URL from api.key
        
    Returns:
        str: Space ID or None if not found
        
    Example:
        https://chat.googleapis.com/v1/spaces/AAQA_zvdsdQ/messages?key=...
        Returns: AAQA_zvdsdQ
    """
    match = re.search(r'/spaces/([^/]+)/', webhookUrl)
    return match.group(1) if match else None


def getShowFromSpaceId(spaceId):
    """Get show code for a Space ID.
    
    Args:
        spaceId: Google Chat Space ID
        
    Returns:
        str: Show code or None if Space not configured
    """
    config = loadSpaceConfig()
    spaceConfig = config.get(spaceId)
    
    if spaceConfig:
        return spaceConfig.get('show')
    
    return None


def setShowForSpace(spaceId, showCode, spaceName=None):
    """Set show code for a Space ID.
    
    Args:
        spaceId: Google Chat Space ID
        showCode: ShotGrid show code (e.g., "lbp3")
        spaceName: Optional human-readable Space name
        
    Returns:
        bool: True if saved successfully
    """
    config = loadSpaceConfig()
    
    config[spaceId] = {
        'show': showCode,
        'name': spaceName or f"Space {spaceId}",
        'configured_at': datetime.utcnow().isoformat() + 'Z'
    }
    
    try:
        saveSpaceConfig(config)
        return True
    except Exception:
        return False


def getSpaceIdFromApiKey():
    """Get Space ID from webhook URL in api.key file.
    
    Returns:
        str: Space ID or None if not found
    """
    projectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    apiKeyPath = os.path.join(projectRoot, 'api.key')
    
    if not os.path.exists(apiKeyPath):
        return None
    
    webhookUrl = None
    
    with open(apiKeyPath, 'r') as fileHandle:
        for line in fileHandle:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                
                if key == 'SPACE_WEBHOOK':
                    webhookUrl = value
                    break
    
    if webhookUrl:
        return getSpaceIdFromWebhook(webhookUrl)
    
    return None
