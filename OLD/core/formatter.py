"""Reply formatting for bot messages.

Formats clean, concise bot replies for Google Spaces.
"""


def formatBotReply(mention, shotCode, note, sgResult):
    """Format a bot reply for Google Space.

    Args:
        mention: Person mentioned (string, e.g., "Louis Pare")
        shotCode: Shot/asset code (string, e.g., "306dtt_1440")
        note: Note text (string)
        sgResult: ShotGrid lookup result dict from lookupEntity()

    Returns:
        Formatted reply string for posting to Space.

    Examples:
        >>> formatBotReply("Louis Pare", "306dtt_1440", "not seeing MP", {...})
        '✅ Message recorded\\n\\n@Louis Paré — please check 306dtt_1440\\n"not seeing MP"\\n\\n→ ShotGrid\\nTicket sent to CG Dashboard'
    """
    lines = []

    # Header
    lines.append('✅ Message recorded')
    lines.append('')

    # Tag person and shot code
    if mention and shotCode:
        # Add accent to Louis Pare if needed
        displayName = mention
        if mention.lower() == 'louis pare':
            displayName = 'Louis Paré'

        lines.append(f'@{displayName} — please check {shotCode}')

        # Add note if present
        if note:
            # Extract a clean quote from the note (remove shot code)
            cleanNote = note.replace(shotCode, '').strip()
            if cleanNote:
                lines.append(f'"{cleanNote}"')
        lines.append('')

    # ShotGrid info (if found)
    if sgResult and sgResult.get('found'):
        entityType = sgResult.get('type')
        status = sgResult.get('status')
        link = sgResult.get('link')

        if status:
            lines.append(f'{entityType} status: {status}')

        if link:
            lines.append('')
            lines.append('→ ShotGrid')
            lines.append(link)
    else:
        # Entity not found
        if shotCode:
            lines.append(f'⚠️ Could not find {shotCode} in ShotGrid')
            lines.append('Please verify the shot/asset code')

    # Footer
    lines.append('')
    lines.append('Ticket sent to CG Dashboard')

    return '\n'.join(lines)


def formatAcknowledgment(mention, shotCode, note):
    """Format a simple acknowledgment without ShotGrid lookup.

    Args:
        mention: Person mentioned (string)
        shotCode: Shot/asset code (string)
        note: Note text (string)

    Returns:
        Formatted acknowledgment string.
    """
    lines = []
    lines.append('✅ Message recorded')
    lines.append('')

    if mention:
        displayName = mention
        if mention.lower() == 'louis pare':
            displayName = 'Louis Paré'

        actionText = f'@{displayName}'
        if shotCode:
            actionText += f' — please check {shotCode}'
        lines.append(actionText)

    if note:
        lines.append(f'"{note}"')

    lines.append('')
    lines.append('Ticket sent to CG Dashboard')

    return '\n'.join(lines)


def formatShotGridLink(entityType, entityId, baseUrl):
    """Format a ShotGrid entity link.

    Args:
        entityType: Entity type (e.g., 'Shot', 'Asset', 'Version')
        entityId: Entity ID (int)
        baseUrl: ShotGrid base URL

    Returns:
        Full ShotGrid URL string.

    Examples:
        >>> formatShotGridLink('Shot', 12345, 'https://rodeofx.shotgrid.autodesk.com')
        'https://rodeofx.shotgrid.autodesk.com/detail/Shot/12345'
    """
    return f"{baseUrl}/detail/{entityType}/{entityId}"


def formatErrorMessage(errorMsg):
    """Format an error message for the bot.

    Args:
        errorMsg: Error description (string)

    Returns:
        Formatted error message string.
    """
    lines = []
    lines.append('⚠️ Error')
    lines.append('')
    lines.append(errorMsg)
    lines.append('')
    lines.append('Please contact Pipeline Support if this persists.')

    return '\n'.join(lines)
