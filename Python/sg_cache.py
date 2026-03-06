"""
Simple in-memory cache for ShotGrid queries with TTL.
"""

import time
import hashlib
import json
from typing import Any, Optional


class ShotGridCache:
    """In-memory cache for ShotGrid API results with time-to-live."""
    
    def __init__(self, ttlSeconds=300):
        """Initialize cache.
        
        Args:
            ttlSeconds: Time-to-live in seconds (default 5 minutes).
        """
        self.cache = {}
        self.ttl = ttlSeconds
    
    def generateKey(self, entityType, filters, fields):
        """Generate cache key from query parameters.
        
        Args:
            entityType: SG entity type (e.g., 'Asset', 'Version').
            filters: SG filter list.
            fields: SG field list.
            
        Returns:
            str: Hash key for cache lookup.
        """
        keyData = {
            'entity': entityType,
            'filters': str(filters),
            'fields': sorted(fields) if fields else []
        }
        keyString = json.dumps(keyData, sort_keys=True)
        return hashlib.md5(keyString.encode()).hexdigest()
    
    def get(self, key):
        """Retrieve cached value if not expired.
        
        Args:
            key: Cache key.
            
        Returns:
            Cached value or None if expired/missing.
        """
        if key not in self.cache:
            return None
        
        entry = self.cache[key]
        age = time.time() - entry['timestamp']
        
        if age > self.ttl:
            del self.cache[key]
            return None
        
        return entry['data']
    
    def set(self, key, data):
        """Store data in cache with current timestamp.
        
        Args:
            key: Cache key.
            data: Data to cache.
        """
        self.cache[key] = {
            'data': data,
            'timestamp': time.time()
        }
    
    def clear(self):
        """Clear all cached entries."""
        self.cache.clear()
    
    def getStats(self):
        """Get cache statistics.
        
        Returns:
            Dict with entry count and oldest entry age.
        """
        if not self.cache:
            return {'entries': 0, 'oldestAge': 0}
        
        now = time.time()
        ages = [now - entry['timestamp'] for entry in self.cache.values()]
        
        return {
            'entries': len(self.cache),
            'oldestAge': max(ages) if ages else 0
        }


assetAnalyzerCache = ShotGridCache(ttlSeconds=300)
