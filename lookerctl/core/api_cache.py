"""SQLite-backed disk cache for Looker API responses with TTL.

This cache dramatically speeds up operations that fetch large numbers of
dashboards, looks, and other Looker content by caching API responses.

Features:
- SQLite storage for persistent caching
- Configurable TTL per cache entry
- Automatic expiration and cleanup
- Thread-safe operations
- Compression for large responses
"""

import gzip
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional


class ApiCache:
    """SQLite-backed cache for Looker API responses."""

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        default_ttl: int = 3600,  # 1 hour default
    ):
        """Initialize API cache.

        Args:
            cache_dir: Directory for cache database (default: ~/.looker_cache)
            default_ttl: Default time-to-live in seconds (default: 1 hour)
        """
        self.cache_dir = cache_dir or Path.home() / ".looker_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "api_cache.db"
        self.default_ttl = default_ttl

        # Initialize database
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database with schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    cache_key TEXT PRIMARY KEY,
                    endpoint TEXT NOT NULL,
                    params_hash TEXT NOT NULL,
                    response_data BLOB NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    hit_count INTEGER DEFAULT 0,
                    compressed INTEGER DEFAULT 1
                )
            """)

            # Index for cleanup queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires_at
                ON cache_entries(expires_at)
            """)

            # Index for endpoint queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_endpoint
                ON cache_entries(endpoint)
            """)

            conn.commit()

    def _make_cache_key(self, endpoint: str, params: dict[str, Any]) -> str:
        """Generate cache key from endpoint and parameters.

        Args:
            endpoint: API endpoint name (e.g., 'all_dashboards')
            params: Parameters passed to the endpoint

        Returns:
            SHA256 hash of endpoint + params
        """
        # Sort params for consistent hashing
        params_str = json.dumps(params, sort_keys=True)
        key_material = f"{endpoint}:{params_str}"
        return hashlib.sha256(key_material.encode()).hexdigest()

    def _compress_data(self, data: Any) -> bytes:
        """Compress data using gzip.

        Args:
            data: Data to compress (will be JSON-serialized)

        Returns:
            Compressed bytes
        """
        json_str = json.dumps(data)
        return gzip.compress(json_str.encode(), compresslevel=6)

    def _decompress_data(self, compressed: bytes) -> Any:
        """Decompress and deserialize data.

        Args:
            compressed: Compressed bytes

        Returns:
            Deserialized data
        """
        json_str = gzip.decompress(compressed).decode()
        return json.loads(json_str)

    def get(self, endpoint: str, params: Optional[dict[str, Any]] = None) -> Optional[Any]:
        """Get cached response if available and not expired.

        Args:
            endpoint: API endpoint name
            params: Parameters passed to the endpoint

        Returns:
            Cached response data, or None if not cached/expired
        """
        params = params or {}
        cache_key = self._make_cache_key(endpoint, params)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT response_data, expires_at, compressed
                FROM cache_entries
                WHERE cache_key = ? AND expires_at > ?
                """,
                (cache_key, int(time.time())),
            )

            row = cursor.fetchone()
            if row is None:
                return None

            response_data, expires_at, compressed = row

            # Update hit count
            conn.execute(
                """
                UPDATE cache_entries
                SET hit_count = hit_count + 1
                WHERE cache_key = ?
                """,
                (cache_key,),
            )
            conn.commit()

            # Decompress if needed
            if compressed:
                return self._decompress_data(response_data)
            else:
                return json.loads(response_data.decode())

    def set(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]],
        response: Any,
        ttl: Optional[int] = None,
    ) -> None:
        """Cache API response.

        Args:
            endpoint: API endpoint name
            params: Parameters passed to the endpoint
            response: Response data to cache
            ttl: Time-to-live in seconds (uses default if not specified)
        """
        params = params or {}
        cache_key = self._make_cache_key(endpoint, params)
        params_hash = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]

        ttl = ttl if ttl is not None else self.default_ttl
        now = int(time.time())
        expires_at = now + ttl

        # Compress the response
        compressed_data = self._compress_data(response)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cache_entries
                (cache_key, endpoint, params_hash, response_data,
                 created_at, expires_at, hit_count, compressed)
                VALUES (?, ?, ?, ?, ?, ?, 0, 1)
                """,
                (
                    cache_key,
                    endpoint,
                    params_hash,
                    compressed_data,
                    now,
                    expires_at,
                ),
            )
            conn.commit()

    def invalidate(
        self, endpoint: Optional[str] = None, params: Optional[dict[str, Any]] = None
    ) -> int:
        """Invalidate cached entries.

        Args:
            endpoint: If specified, only invalidate this endpoint
            params: If specified (with endpoint), invalidate specific params

        Returns:
            Number of entries invalidated
        """
        with sqlite3.connect(self.db_path) as conn:
            if endpoint and params:
                # Invalidate specific cache entry
                cache_key = self._make_cache_key(endpoint, params)
                cursor = conn.execute("DELETE FROM cache_entries WHERE cache_key = ?", (cache_key,))
            elif endpoint:
                # Invalidate all entries for this endpoint
                cursor = conn.execute("DELETE FROM cache_entries WHERE endpoint = ?", (endpoint,))
            else:
                # Invalidate all entries
                cursor = conn.execute("DELETE FROM cache_entries")

            deleted = cursor.rowcount
            conn.commit()
            return deleted

    def invalidate_by_id(self, endpoint: str, id_param: str, id_value: str) -> int:
        """Invalidate cache entries matching a specific ID.

        This clears all cached variants of a resource (different field sets).

        Args:
            endpoint: Endpoint name (e.g., 'dashboard', 'query')
            id_param: Parameter name (e.g., 'dashboard_id', 'query_id')
            id_value: ID value to match

        Returns:
            Number of entries invalidated

        Examples:
            # Clear specific dashboard (all field variants)
            cache.invalidate_by_id('dashboard', 'dashboard_id', '123')

            # Clear specific query
            cache.invalidate_by_id('query', 'query_id', '456')
        """
        deleted = 0
        with sqlite3.connect(self.db_path) as conn:
            # Try common parameter combinations for this ID
            # This covers different field sets that might be cached
            param_combinations = [
                {id_param: id_value},
                {id_param: id_value, "fields": None},
            ]

            # Add common field combinations for dashboards/queries
            if endpoint in ("dashboard", "dashboard_lookml"):
                param_combinations.extend(
                    [
                        {id_param: id_value, "fields": "id"},
                        {id_param: id_value, "fields": "id,title"},
                        {id_param: id_value, "fields": "id,title,dashboard_elements"},
                        {id_param: id_value, "fields": "id,title,user_id,folder"},
                    ]
                )

            for params in param_combinations:
                cache_key = self._make_cache_key(endpoint, params)
                result = conn.execute("DELETE FROM cache_entries WHERE cache_key = ?", (cache_key,))
                deleted += result.rowcount

            conn.commit()
            return deleted

    def cleanup_expired(self) -> int:
        """Remove expired cache entries.

        Returns:
            Number of entries removed
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM cache_entries WHERE expires_at <= ?",
                (int(time.time()),),
            )
            deleted = cursor.rowcount
            conn.commit()
            return deleted

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        with sqlite3.connect(self.db_path) as conn:
            # Total entries
            total = conn.execute("SELECT COUNT(*) FROM cache_entries").fetchone()[0]

            # Expired entries
            expired = conn.execute(
                "SELECT COUNT(*) FROM cache_entries WHERE expires_at <= ?",
                (int(time.time()),),
            ).fetchone()[0]

            # Total hits
            total_hits = conn.execute("SELECT SUM(hit_count) FROM cache_entries").fetchone()[0] or 0

            # Size on disk
            db_size = self.db_path.stat().st_size if self.db_path.exists() else 0

            # Entries by endpoint
            endpoint_counts = {}
            for row in conn.execute(
                "SELECT endpoint, COUNT(*) FROM cache_entries GROUP BY endpoint"
            ):
                endpoint_counts[row[0]] = row[1]

            return {
                "total_entries": total,
                "expired_entries": expired,
                "active_entries": total - expired,
                "total_hits": total_hits,
                "db_size_bytes": db_size,
                "db_size_mb": db_size / (1024 * 1024),
                "endpoints": endpoint_counts,
            }

    def vacuum(self) -> None:
        """Optimize database by running VACUUM."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("VACUUM")
            conn.commit()
