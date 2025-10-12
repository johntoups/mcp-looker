"""Looker SDK client wrapper - simple and clean."""

from pathlib import Path
from typing import Any, Optional

import looker_sdk
from looker_sdk.sdk.api40 import methods, models
from rich.console import Console

from lookerctl.core.api_cache import ApiCache
from lookerctl.core.session_storage import get_preferred_workspace

console = Console()


def _to_json_serializable(obj: Any) -> Any:
    """Recursively convert Looker SDK objects to JSON-serializable dicts.

    The SDK's dict() method doesn't recursively convert nested objects,
    so we need to handle that ourselves.

    Args:
        obj: Object to convert (can be SDK object, list, dict, or primitive)

    Returns:
        JSON-serializable version of the object
    """
    # Handle None
    if obj is None:
        return None

    # Handle primitives (str, int, float, bool)
    if isinstance(obj, (str, int, float, bool)):
        return obj

    # Handle lists
    if isinstance(obj, list):
        return [_to_json_serializable(item) for item in obj]

    # Handle dicts
    if isinstance(obj, dict):
        return {key: _to_json_serializable(value) for key, value in obj.items()}

    # Handle SDK objects - they have __dict__ or can be converted with dict()
    if hasattr(obj, "__dict__"):
        # Use vars() to get object's __dict__ and recursively convert
        return {
            key: _to_json_serializable(value)
            for key, value in vars(obj).items()
            if not key.startswith("_")  # Skip private attributes
        }

    # Fallback: try to convert to string
    return str(obj)


class LookerClient:
    """
    Simple wrapper around Looker SDK.

    Reads configuration from LOOKERSDK_* environment variables.
    No manual auth needed - the SDK handles everything.

    Automatically switches to the user's preferred workspace (stored in .looker_session.json).
    Defaults to 'dev' workspace for safety.

    Features SQLite-backed caching for expensive API calls (dashboards, looks, etc.)
    with configurable TTL.
    """

    def __init__(
        self,
        use_cache: bool = True,
        cache_ttl: int = 3600,  # 1 hour default
        cache_dir: Optional[Path] = None,
    ):
        """Initialize Looker SDK client.

        Args:
            use_cache: Enable API response caching (default: True)
            cache_ttl: Cache TTL in seconds (default: 3600 = 1 hour)
            cache_dir: Cache directory (default: ~/.looker_cache)
        """
        self._sdk: Optional[methods.Looker40SDK] = None
        self._workspace_initialized = False

        # API cache
        self.use_cache = use_cache
        self.cache_ttl = cache_ttl
        self._cache: Optional[ApiCache] = None
        if use_cache:
            self._cache = ApiCache(cache_dir=cache_dir, default_ttl=cache_ttl)

    @property
    def sdk(self) -> methods.Looker40SDK:
        """
        Get authenticated Looker SDK instance.

        The SDK automatically reads from LOOKERSDK_* environment variables.
        On first access, switches to the user's preferred workspace.
        """
        if self._sdk is None:
            self._sdk = looker_sdk.init40()
            # Test authentication
            user = self._sdk.me()
            console.print(f"[green]✓[/green] Authenticated as: {user.display_name or user.email}")

            # Switch to preferred workspace
            if not self._workspace_initialized:
                self._initialize_workspace()
                self._workspace_initialized = True

        return self._sdk

    def _initialize_workspace(self) -> None:
        """Switch to the user's preferred workspace on initialization."""
        if self._sdk is None:
            return

        preferred_workspace = get_preferred_workspace()

        try:
            # Check current workspace
            session = self._sdk.session()
            current_workspace = session.workspace_id or "production"

            # Only switch if different
            if current_workspace != preferred_workspace:
                self._sdk.update_session(
                    body=models.WriteApiSession(workspace_id=preferred_workspace)
                )
                console.print(f"[dim]Switched to {preferred_workspace} workspace[/dim]")
        except Exception:
            # Silently fail - workspace switching is not critical
            pass

    # Convenience methods that delegate to the SDK

    def get_session(self) -> Any:
        """Get current session information."""
        return self.sdk.session()

    def get_all_projects(self) -> list[Any]:
        """Get all Looker projects."""
        return self.sdk.all_projects()

    def get_project(self, project_id: str) -> Any:
        """Get project by ID."""
        return self.sdk.project(project_id)

    def validate_project(self, project_id: str) -> Any:
        """Validate LookML project."""
        return self.sdk.validate_project(project_id)

    def get_all_lookml_models(self) -> list[Any]:
        """Get all LookML models."""
        return self.sdk.all_lookml_models()

    def get_lookml_model(self, model_name: str) -> Any:
        """Get LookML model by name."""
        return self.sdk.lookml_model(model_name)

    def get_lookml_model_explore(self, model_name: str, explore_name: str) -> Any:
        """Get explore details from a model."""
        return self.sdk.lookml_model_explore(model_name, explore_name)

    # Cached API methods for expensive operations

    def get_all_dashboards_cached(
        self, fields: Optional[str] = None, use_cache: Optional[bool] = None
    ) -> list[Any]:
        """Get all dashboards with caching.

        Args:
            fields: Specific fields to return
            use_cache: Override instance cache setting

        Returns:
            List of dashboard objects
        """
        should_cache = use_cache if use_cache is not None else self.use_cache

        if should_cache and self._cache:
            params = {"fields": fields}
            cached = self._cache.get("all_dashboards", params)
            if cached is not None:
                console.print("  [dim]Loaded dashboards from cache[/dim]")
                # Convert back to SDK objects
                try:
                    return [models.Dashboard(**d) for d in cached]
                except (TypeError, KeyError):
                    # Cache corruption - invalidate and re-fetch
                    console.print("  [dim]Cache corrupted, re-fetching...[/dim]")
                    self._cache.invalidate("all_dashboards", params)

        # Fetch from API
        console.print("  [dim]Fetching dashboards from API...[/dim]")
        dashboards = self.sdk.all_dashboards(fields=fields)

        # Cache the response
        if should_cache and self._cache:
            # Serialize to dict for caching - recursively handle nested objects
            dashboard_dicts = [_to_json_serializable(d) for d in dashboards]
            self._cache.set("all_dashboards", params, dashboard_dicts, ttl=self.cache_ttl)

        return dashboards

    def get_all_looks_cached(
        self, fields: Optional[str] = None, use_cache: Optional[bool] = None
    ) -> list[Any]:
        """Get all looks with caching.

        Args:
            fields: Specific fields to return
            use_cache: Override instance cache setting

        Returns:
            List of look objects
        """
        should_cache = use_cache if use_cache is not None else self.use_cache

        if should_cache and self._cache:
            params = {"fields": fields}
            cached = self._cache.get("all_looks", params)
            if cached is not None:
                console.print("  [dim]Loaded looks from cache[/dim]")
                # Convert back to SDK objects
                try:
                    return [models.Look(**l_) for l_ in cached]
                except (TypeError, KeyError):
                    # Cache corruption - invalidate and re-fetch
                    console.print("  [dim]Cache corrupted, re-fetching...[/dim]")
                    self._cache.invalidate("all_looks", params)

        # Fetch from API
        console.print("  [dim]Fetching looks from API...[/dim]")
        looks = self.sdk.all_looks(fields=fields)

        # Cache the response
        if should_cache and self._cache:
            # Serialize to dict for caching - recursively handle nested objects
            look_dicts = [_to_json_serializable(l_) for l_ in looks]
            self._cache.set("all_looks", params, look_dicts, ttl=self.cache_ttl)

        return looks

    def get_dashboard_cached(
        self, dashboard_id: str, fields: Optional[str] = None, use_cache: Optional[bool] = None
    ) -> Any:
        """Get specific dashboard with caching.

        This is THE critical method - caches individual dashboard details.
        With 15K dashboards, this saves ~1 hour on repeated runs.

        Args:
            dashboard_id: Dashboard ID
            fields: Specific fields to return
            use_cache: Override instance cache setting

        Returns:
            Dashboard object
        """
        should_cache = use_cache if use_cache is not None else self.use_cache

        if should_cache and self._cache:
            params = {"dashboard_id": dashboard_id, "fields": fields}
            cached = self._cache.get("dashboard", params)
            if cached is not None:
                try:
                    return models.Dashboard(**cached)
                except (TypeError, KeyError):
                    # Cache corruption or schema mismatch - invalidate and re-fetch
                    self._cache.invalidate("dashboard", params)

        # Fetch from API
        dashboard = self.sdk.dashboard(dashboard_id, fields=fields)

        # Cache the response - ALWAYS update cache on every call
        if should_cache and self._cache:
            params = {"dashboard_id": dashboard_id, "fields": fields}
            self._cache.set(
                "dashboard", params, _to_json_serializable(dashboard), ttl=self.cache_ttl
            )

        return dashboard

    def get_query_cached(self, query_id: int | str, use_cache: Optional[bool] = None) -> Any:
        """Get query details with caching.

        This is THE other critical method - caches query details.
        Queries are referenced by dashboards and looks, so this gets hit A LOT.

        Args:
            query_id: Query ID (int or str)
            use_cache: Override instance cache setting

        Returns:
            Query object
        """
        should_cache = use_cache if use_cache is not None else self.use_cache

        # Normalize query_id to string for consistent caching
        query_id_str = str(query_id)

        if should_cache and self._cache:
            params = {"query_id": query_id_str}
            cached = self._cache.get("query", params)
            if cached is not None:
                try:
                    # Query requires model and view - ensure they exist
                    # Provide defaults if missing (shouldn't happen with proper API responses)
                    cached.setdefault("model", "")
                    cached.setdefault("view", "")
                    return models.Query(**cached)  # type: ignore[arg-type]
                except (TypeError, KeyError):
                    # Cache corruption or schema mismatch - invalidate and re-fetch
                    self._cache.invalidate("query", params)

        # Fetch from API
        query = self.sdk.query(query_id)

        # Cache the response - ALWAYS update cache on every call
        if should_cache and self._cache:
            params = {"query_id": query_id_str}
            self._cache.set("query", params, _to_json_serializable(query), ttl=self.cache_ttl)

        return query

    def get_dashboard_lookml_cached(
        self, dashboard_id: str, use_cache: Optional[bool] = None
    ) -> Any:
        """Get dashboard LookML with caching.

        Used when exporting dashboards - another expensive operation.

        Args:
            dashboard_id: Dashboard ID
            use_cache: Override instance cache setting

        Returns:
            DashboardLookML object
        """
        should_cache = use_cache if use_cache is not None else self.use_cache

        if should_cache and self._cache:
            params = {"dashboard_id": dashboard_id}
            cached = self._cache.get("dashboard_lookml", params)
            if cached is not None:
                try:
                    return models.DashboardLookml(**cached)
                except (TypeError, KeyError):
                    # Cache corruption - invalidate and re-fetch
                    self._cache.invalidate("dashboard_lookml", params)

        # Fetch from API
        lookml = self.sdk.dashboard_lookml(dashboard_id)

        # Cache the response - ALWAYS update cache on every call
        if should_cache and self._cache:
            params = {"dashboard_id": dashboard_id}
            self._cache.set(
                "dashboard_lookml", params, _to_json_serializable(lookml), ttl=self.cache_ttl
            )

        return lookml

    def invalidate_cache(self, endpoint: Optional[str] = None) -> int:
        """Invalidate cache entries.

        Args:
            endpoint: Specific endpoint to invalidate (all if None)

        Returns:
            Number of entries invalidated
        """
        if self._cache:
            return self._cache.invalidate(endpoint=endpoint)
        return 0

    def invalidate_cache_by_id(self, endpoint: str, id_param: str, id_value: str) -> int:
        """Invalidate cache entries for a specific resource ID.

        Args:
            endpoint: Endpoint name (e.g., 'dashboard', 'query')
            id_param: Parameter name (e.g., 'dashboard_id', 'query_id')
            id_value: ID value to match

        Returns:
            Number of entries invalidated
        """
        if self._cache:
            return self._cache.invalidate_by_id(endpoint, id_param, id_value)
        return 0

    def get_cache_stats(self) -> Optional[dict[str, Any]]:
        """Get cache statistics.

        Returns:
            Cache statistics dict or None if caching disabled
        """
        if self._cache:
            return self._cache.get_stats()
        return None

    def cleanup_cache(self) -> int:
        """Clean up expired cache entries.

        Returns:
            Number of entries removed
        """
        if self._cache:
            return self._cache.cleanup_expired()
        return 0

    def close(self) -> None:
        """Close the SDK session."""
        if self._sdk is not None:
            self._sdk = None

    def __enter__(self) -> "LookerClient":
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()
