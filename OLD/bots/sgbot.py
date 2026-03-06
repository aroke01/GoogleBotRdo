"""ShotGrid bot logic.

Main bot processing: parse message → query ShotGrid → format reply.
Reusable for both CLI demo and Cloud Run deployment.
"""

from core.parser import parseMessage
from core.shotgrid import lookupEntity
from core.formatter import formatBotReply, formatErrorMessage


def processBotMessage(rawMessage, showCode='lbp3'):
    """Process a Google Space message and generate bot reply.

    This is the main bot logic that ties together:
    1. Message parsing (extract @mention, shot code, note)
    2. ShotGrid lookup
    3. Reply formatting

    Args:
        rawMessage: Raw text from Google Space
        showCode: Show/project code (default: 'lbp3')

    Returns:
        dict with keys:
            - reply: Formatted bot reply string
            - parsed: Parsed message dict
            - sgResult: ShotGrid lookup result dict
            - success: True if processing succeeded

    Examples:
        >>> processBotMessage("Eileen Bocanegra, 10:41 AM\\n306dtt_1440 not seeing MP @Louis Pare")
        {
            'reply': '✅ Message recorded...',
            'parsed': {...},
            'sgResult': {...},
            'success': True
        }
    """
    result = {
        'reply': None,
        'parsed': None,
        'sgResult': None,
        'success': False
    }

    try:
        # Step 1: Parse message
        parsed = parseMessage(rawMessage)
        result['parsed'] = parsed

        if not parsed.get('shotCode'):
            # No shot code found - still acknowledge but no ShotGrid lookup
            reply = formatErrorMessage('Could not find a shot/asset code in the message.')
            result['reply'] = reply
            return result

        # Step 2: Query ShotGrid
        shotCode = parsed['shotCode']
        sgResult = lookupEntity(shotCode, showCode=showCode)
        result['sgResult'] = sgResult

        # Step 3: Format reply
        mention = parsed.get('mention')
        note = parsed.get('note')

        reply = formatBotReply(mention, shotCode, note, sgResult)
        result['reply'] = reply
        result['success'] = True

    except Exception as e:
        # Handle errors gracefully
        errorMsg = f"Error processing message: {str(e)}"
        result['reply'] = formatErrorMessage(errorMsg)

    return result


def handleSpaceMessage(event, showCode='lbp3'):
    """Handle incoming Google Space message event.

    This function is designed to be called by Cloud Run / Apps Script
    when a message is posted to the Space.

    Args:
        event: Google Chat event object (dict)
        showCode: Show/project code (default: 'lbp3')

    Returns:
        dict with 'text' key for bot reply (Google Chat format)

    Examples:
        >>> handleSpaceMessage({'message': {'text': '306dtt_1440 @Louis Pare'}})
        {'text': '✅ Message recorded...'}
    """
    # Extract message text from event
    rawMessage = ''
    if isinstance(event, dict):
        if 'message' in event:
            rawMessage = event['message'].get('text', '')
        elif 'text' in event:
            rawMessage = event['text']

    if not rawMessage:
        return {'text': '⚠️ No message text found'}

    # Process message
    result = processBotMessage(rawMessage, showCode=showCode)

    # Return Google Chat formatted response
    return {'text': result['reply']}
