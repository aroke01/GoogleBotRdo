#!/usr/bin/env python
"""bot_reply.py — Post messages to Google Space via webhook.

Sends formatted messages to Google Chat Space using outgoing webhook.
"""

import os
import requests


def getWebhookUrl():
    """Load Google Space webhook URL from api.key.

    Returns:
        Webhook URL string.

    Raises:
        FileNotFoundError: If api.key not found
        ValueError: If SPACE_WEBHOOK not found in api.key
    """
    # Find api.key in project root
    scriptDir = os.path.dirname(os.path.abspath(__file__))
    keyFile = os.path.join(scriptDir, 'api.key')

    if not os.path.exists(keyFile):
        raise FileNotFoundError(f"api.key not found at {keyFile}")

    # Parse api.key
    config = {}
    with open(keyFile, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip()

    webhookUrl = config.get('SPACE_WEBHOOK')

    if not webhookUrl:
        raise ValueError("SPACE_WEBHOOK not found in api.key")

    return webhookUrl


def postToSpace(message):
    """Post a message to Google Space via webhook.

    Args:
        message: Message text to post (string)

    Returns:
        Response object from requests.post

    Raises:
        requests.RequestException: If webhook POST fails
    """
    webhookUrl = getWebhookUrl()

    payload = {
        'text': message
    }

    response = requests.post(webhookUrl, json=payload)
    response.raise_for_status()

    return response


def main():
    """CLI entry point for posting messages."""
    import sys

    if len(sys.argv) < 2:
        print('Usage: python bot_reply.py "message text"')
        sys.exit(1)

    message = sys.argv[1]

    try:
        postToSpace(message)
        print('✅ Message posted to Space successfully')
    except Exception as e:
        print(f'⚠️ Error posting to Space: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
