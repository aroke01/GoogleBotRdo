"""
Core modules for rdo_googlebot.

Provides message parsing, ShotGrid queries, and reply formatting.
"""

from core.parser import parseMessage, parseAllCodes
from core.shotgrid import lookupEntity, getAssetInfo
from core.formatter import formatReply, formatMultiCodeReply, formatAssetInfo
from core.webhook import postToSpace
from core.config import getShowFromSpaceId, setShowForSpace, getSpaceIdFromApiKey

__all__ = ['parseMessage', 'parseAllCodes', 'lookupEntity', 'getAssetInfo', 'formatReply', 'formatMultiCodeReply', 'formatAssetInfo', 'postToSpace', 'getShowFromSpaceId', 'setShowForSpace', 'getSpaceIdFromApiKey']
