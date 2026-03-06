"""
Google Space webhook module for rdo_googlebot.

Sends messages to Google Chat Space via outgoing webhook.
"""

import os
import requests


def getWebhookUrl():
    """Load Google Space webhook URL from api.key.
    
    Returns:
        str: Webhook URL
        
    Raises:
        ValueError: If SPACE_WEBHOOK not found in api.key
    """
    projectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    apiKeyPath = os.path.join(projectRoot, 'api.key')
    
    if not os.path.exists(apiKeyPath):
        raise FileNotFoundError(f"api.key not found at {apiKeyPath}")
    
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
    
    if not webhookUrl:
        raise ValueError("SPACE_WEBHOOK not found in api.key. Add: SPACE_WEBHOOK=https://...")
    
    return webhookUrl


def postToSpace(message):
    """Post a message to Google Space via webhook.
    
    Args:
        message: Message text to post
        
    Returns:
        requests.Response: Response object
        
    Raises:
        requests.RequestException: If webhook POST fails
    """
    webhookUrl = getWebhookUrl()
    
    payload = {'text': message}
    
    response = requests.post(webhookUrl, json=payload, timeout=10)
    
    if response.status_code != 200:
        print(f"Webhook error response: {response.text}")
    
    response.raise_for_status()
    
    return response
