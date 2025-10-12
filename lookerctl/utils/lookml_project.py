"""LookML project representation with in-memory graph for fast queries and validation.

This module provides:
- LookMLProject: In-memory representation of entire LookML project
- Fast field resolution for explores (no API calls needed)
- Local validation of field references
- Dependency graph traversal
- View inheritance resolution
- Incremental parsing with pickle caching for performance
"""

import pickle
from pathlib import Path
from typing import Any, Optional

import networkx as nx
from rich.console import Console

from lookerctl.utils.lookml_parser import LookMLProjectParser
from lookerctl.utils.lookml_types import (
    Constant,
    Dashboard,
    Explore,
    Field,
    FieldReference,
    FieldType,
    Model,
    Refinement,
    ValidationError,
    View,
)


class LookMLProject:
    """In-memory representation of a LookML project with dependency graph.

    Supports incremental parsing with pickle caching for performance.
    """

    CACHE_VERSION = 1  # Increment when cache format changes

    def __init__(
        self,
        project_path: Path,
        include_fields: bool = False,
        use_cache: bool = True,
        cache_dir: Optional[Path] = None,
        console: Optional[Console] = None,
    ):
        """Initialize project by parsing all LookML files.

        Args:
            project_path: Path to LookML project directory
            include_fields: If True, include field-level nodes in dependency graph
            use_cache: If True, use pickle cache for incremental parsing
            cache_dir: Directory for cache files (default: project_path/.looker_cache)
            console: Optional console for output messages
        """
        self.project_path = project_path.resolve()
        self.parser = LookMLProjectParser()
        self.include_fields = include_fields
        self.console = console or Console()

        # File modification time tracking for incremental parsing
        self.file_mtimes: dict[Path, float] = {}

        # Cache configuration
        self.use_cache = use_cache
        self.cache_dir = cache_dir or (self.project_path / ".looker_cache")
        self.cache_file = self.cache_dir / "project.pkl"

        # Try to load from cache first
        if use_cache and self._load_from_cache():
            # Cache loaded successfully, only parse changed files
            self._incremental_parse()
        else:
            # Full parse needed
            self._full_parse()

        # Cache for resolved views (with extends applied)
        # Must be initialized before _build_graph() since field node creation needs it
        self._resolved_views: dict[str, View] = {}

        # Apply refinements (merge +view with base view)
        self._apply_refinements()

        # Build dependency graph
        self.graph = self._build_graph()

        # Save to cache if enabled
        if use_cache:
            self._save_to_cache()

    def _full_parse(self) -> None:
        """Perform a full parse of all files."""
        parsed = self.parser.parse_directory(self.project_path)

        # Store parsed data
        self.views: dict[str, View] = parsed["views"]
        self.explores: dict[str, Explore] = parsed["explores"]
        self.models: dict[str, Model] = parsed["models"]
        self.constants: dict[str, Constant] = parsed["constants"]
        self.refinements: list[Refinement] = parsed["refinements"]
        self.dashboards: dict[str, "Dashboard"] = parsed["dashboards"]
        self.files: dict[Path, dict[str, Any]] = parsed["files"]

        # Update mtimes
        for file_path in parsed["files"].keys():
            if file_path.exists():
                self.file_mtimes[file_path] = file_path.stat().st_mtime

    def _incremental_parse(self) -> None:
        """Parse only files that have changed since last cache."""
        # Scan directory for all .lkml files
        current_files = set(self.project_path.rglob("*.lkml"))
        cached_files = set(self.file_mtimes.keys())

        # Find new, modified, and deleted files
        new_files = current_files - cached_files
        deleted_files = cached_files - current_files
        modified_files = {
            f
            for f in current_files & cached_files
            if f.stat().st_mtime > self.file_mtimes.get(f, 0)
        }

        changed_files = new_files | modified_files

        if not changed_files and not deleted_files:
            # No changes, use cached data as-is
            return

        self.console.print(
            f"[dim]Incremental update: {len(new_files)} new, {len(modified_files)} modified, {len(deleted_files)} deleted[/dim]"
        )

        # Remove deleted files from collections
        for file_path in deleted_files:
            if file_path in self.files:
                file_data = self.files[file_path]
                # Remove views from this file
                for view_name in [v.name for v in file_data.get("views", [])]:
                    self.views.pop(view_name, None)
                # Remove explores
                for explore_name in [e.name for e in file_data.get("explores", [])]:
                    self.explores.pop(explore_name, None)
                # Remove models
                for model_name in [m.name for m in file_data.get("models", [])]:
                    self.models.pop(model_name, None)
                # Remove constants
                for constant_name in [c.name for c in file_data.get("constants", [])]:
                    self.constants.pop(constant_name, None)
                # Remove dashboards
                for dashboard_name in [d.name for d in file_data.get("dashboards", [])]:
                    self.dashboards.pop(dashboard_name, None)

                del self.files[file_path]
                del self.file_mtimes[file_path]

        # Parse changed files
        for file_path in changed_files:
            try:
                parsed = self.parser.parser.parse_file(file_path)

                # Update collections
                for view in parsed.get("views", []):
                    self.views[view.name] = view
                for explore in parsed.get("explores", []):
                    self.explores[explore.name] = explore
                for model in parsed.get("models", []):
                    self.models[model.name] = model
                for constant in parsed.get("constants", []):
                    self.constants[constant.name] = constant
                for dashboard in parsed.get("dashboards", []):
                    self.dashboards[dashboard.name] = dashboard

                # Refinements need to be rebuilt (they can reference across files)
                # For now, we'll do a simple append
                self.refinements.extend(parsed.get("refinements", []))

                self.files[file_path] = parsed
                self.file_mtimes[file_path] = file_path.stat().st_mtime

            except Exception as e:
                self.console.print(f"Warning: Failed to parse {file_path}: {e}")
                continue

    def _get_cache_key(self) -> str:
        """Generate cache key based on project path and settings."""
        return f"{self.project_path.name}_{self.include_fields}_{self.CACHE_VERSION}"

    def _load_from_cache(self) -> bool:
        """Load project from pickle cache if valid.

        Returns:
            True if cache was loaded successfully, False otherwise
        """
        if not self.cache_file.exists():
            return False

        try:
            with open(self.cache_file, "rb") as f:
                cached_data = pickle.load(f)

            # Validate cache version
            if cached_data.get("version") != self.CACHE_VERSION:
                self.console.print("[dim]Cache version mismatch, rebuilding...[/dim]")
                return False

            if cached_data.get("include_fields") != self.include_fields:
                self.console.print("[dim]Cache field settings mismatch, rebuilding...[/dim]")
                return False

            # Restore state
            self.views = cached_data["views"]
            self.explores = cached_data["explores"]
            self.models = cached_data["models"]
            self.constants = cached_data["constants"]
            self.refinements = cached_data["refinements"]
            self.dashboards = cached_data["dashboards"]
            self.files = cached_data["files"]
            self.file_mtimes = cached_data["file_mtimes"]

            self.console.print(
                f"[dim]Loaded from cache: {len(self.views)} views, {len(self.explores)} explores, {len(self.dashboards)} dashboards[/dim]\n"
            )
            return True

        except Exception as e:
            self.console.print(f"[dim]Failed to load cache: {e}, rebuilding...[/dim]")
            return False

    def _save_to_cache(self) -> None:
        """Save project to pickle cache."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

            cache_data = {
                "version": self.CACHE_VERSION,
                "include_fields": self.include_fields,
                "views": self.views,
                "explores": self.explores,
                "models": self.models,
                "constants": self.constants,
                "refinements": self.refinements,
                "dashboards": self.dashboards,
                "files": self.files,
                "file_mtimes": self.file_mtimes,
            }

            with open(self.cache_file, "wb") as f:
                pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)

        except Exception as e:
            self.console.print(f"[dim]Warning: Failed to save cache: {e}[/dim]")

    def _build_graph(self) -> nx.DiGraph:
        """Build dependency graph of views and explores with qualified node names.

        Nodes are named with type prefixes: 'view.name' and 'explore.name'
        If include_fields is True, also adds field nodes: 'view.name.field.field_name'
        This prevents name collisions and makes the graph self-documenting.
        """
        graph = nx.DiGraph()

        # Add all views as nodes with qualified names
        for view_name in self.views:
            qualified_name = f"view.{view_name}"
            graph.add_node(qualified_name, type="view", base_name=view_name)

        # Add all explores as nodes with qualified names
        for explore_name in self.explores:
            qualified_name = f"explore.{explore_name}"
            graph.add_node(qualified_name, type="explore", base_name=explore_name)

        # Add view dependencies (extends)
        for view_name, view in self.views.items():
            qualified_view = f"view.{view_name}"

            for extended_view in view.extends:
                if extended_view in self.views:
                    qualified_extended = f"view.{extended_view}"
                    graph.add_edge(qualified_view, qualified_extended, relation="extends")

            # Add field reference dependencies
            dependencies = self.parser.find_view_dependencies(view)
            for dep in dependencies:
                if dep in self.views and dep != view_name:
                    qualified_dep = f"view.{dep}"
                    graph.add_edge(qualified_view, qualified_dep, relation="references")

        # Add explore dependencies
        for explore_name, explore in self.explores.items():
            qualified_explore = f"explore.{explore_name}"
            deps = self.parser.find_explore_dependencies(explore)

            # Link to base view
            base_view = deps["base_view"]
            if base_view in self.views:
                qualified_base = f"view.{base_view}"
                graph.add_edge(qualified_explore, qualified_base, relation="base_view")

            # Link to joined views
            for joined_view in deps["joined_views"]:
                if joined_view in self.views:
                    qualified_joined = f"view.{joined_view}"
                    graph.add_edge(qualified_explore, qualified_joined, relation="joins")

        # Add dashboard nodes and their dependencies
        for dashboard_name, dashboard in self.dashboards.items():
            qualified_dashboard = f"dashboard.{dashboard_name}"
            graph.add_node(
                qualified_dashboard,
                type="dashboard",
                base_name=dashboard_name,
                title=dashboard.title,
            )

            # Link dashboards to explores they use
            for explore_ref in dashboard.get_explore_references():
                # explore_ref is in format "model.explore"
                model_name, explore_name = (
                    explore_ref.split(".", 1) if "." in explore_ref else (None, explore_ref)
                )

                # Find the explore in our explores dict
                if explore_name in self.explores:
                    qualified_explore = f"explore.{explore_name}"
                    graph.add_edge(
                        qualified_dashboard,
                        qualified_explore,
                        relation="uses_explore",
                        model=model_name,
                    )

        # Optionally add field-level nodes and dependencies
        if self.include_fields:
            self._add_field_nodes_to_graph(graph)

        return graph

    def _add_field_nodes_to_graph(self, graph: nx.DiGraph) -> None:
        """Add field-level nodes and dependencies to the graph.

        Field nodes are named: 'view.{view_name}.field.{field_name}'
        This creates edges from fields to:
        - The view/explore they belong to
        - Other fields they reference in SQL expressions
        """
        # Add field nodes for all views
        for view_name, view in self.views.items():
            qualified_view = f"view.{view_name}"

            for field in view.fields:
                # Create qualified field node name
                qualified_field = f"view.{view_name}.field.{field.name}"

                # Add field node
                graph.add_node(
                    qualified_field,
                    type="field",
                    field_type=field.field_type.value,
                    view_name=view_name,
                    field_name=field.name,
                )

                # Link field to its parent view
                graph.add_edge(qualified_view, qualified_field, relation="contains")

                # Extract and link field references from SQL
                if field.sql:
                    refs = self.parser.parser.extract_field_references(field.sql)
                    for ref in refs:
                        # Determine the referenced view
                        if ref.is_local():
                            ref_view_name = view_name
                        else:
                            ref_view_name = ref.view_name

                        # Create qualified field reference
                        if ref_view_name and ref_view_name in self.views:
                            ref_field_node = f"view.{ref_view_name}.field.{ref.field_name}"

                            # Only add edge if the referenced field node exists or will exist
                            # (we're iterating through all views, so it will exist)
                            graph.add_edge(qualified_field, ref_field_node, relation="references")

        # Add field nodes for explores (based on available fields)
        for explore_name, explore in self.explores.items():
            qualified_explore = f"explore.{explore_name}"

            # Get all fields available in this explore
            explore_fields = self.get_explore_fields(explore_name, include_hidden=True)

            for field_category in explore_fields.values():
                for field in field_category:
                    # Determine which view this field comes from
                    # Field names are often qualified like "view_name.field_name"
                    if "." in field.name:
                        # Already qualified
                        source_view = field.name.split(".")[0]
                        field_name = field.name.split(".", 1)[1]
                    else:
                        # Unqualified - comes from base view
                        source_view = explore.get_base_view_name()
                        field_name = field.name

                    # Create qualified field node name for explore context
                    qualified_field = f"explore.{explore_name}.field.{source_view}.{field_name}"

                    # Add field node if not already exists
                    if qualified_field not in graph:
                        graph.add_node(
                            qualified_field,
                            type="explore_field",
                            field_type=field.field_type.value,
                            explore_name=explore_name,
                            source_view=source_view,
                            field_name=field_name,
                        )

                    # Link field to its parent explore
                    graph.add_edge(qualified_explore, qualified_field, relation="exposes")

                    # Link to the underlying view field
                    view_field_node = f"view.{source_view}.field.{field_name}"
                    if view_field_node in graph:
                        graph.add_edge(qualified_field, view_field_node, relation="uses")

    def get_view(self, view_name: str, resolve_extends: bool = True) -> Optional[View]:
        """Get a view by name, optionally resolving extends.

        This method:
        1. Resolves extends chain (if enabled)
        2. Expands dimension_group fields into timeframe fields

        Args:
            view_name: Name of view
            resolve_extends: If True, merge fields from extended views

        Returns:
            View object, or None if not found
        """
        if view_name not in self.views:
            return None

        if not resolve_extends:
            return self.views[view_name]

        # Check cache
        if view_name in self._resolved_views:
            return self._resolved_views[view_name]

        # Resolve extends chain
        resolved = self._resolve_view_extends(view_name)

        # Expand dimension_group fields
        resolved = self._expand_dimension_groups(resolved)

        self._resolved_views[view_name] = resolved
        return resolved

    def _resolve_view_extends(self, view_name: str) -> View:
        """Resolve view inheritance by merging fields from extended views."""
        view = self.views[view_name]

        if not view.extends:
            return view

        # Build inheritance chain (depth-first)
        all_fields: dict[str, Field] = {}

        def collect_fields(current_name: str, visited: set[str]):
            if current_name in visited:
                # Circular extends - just skip
                return
            visited.add(current_name)

            current_view = self.views.get(current_name)
            if not current_view:
                return

            # First collect from extended views (they get overridden)
            for extended in current_view.extends:
                collect_fields(extended, visited)

            # Then add this view's fields (override parent fields)
            for field in current_view.fields:
                all_fields[field.name] = field

        collect_fields(view_name, set())

        # Create new view with merged fields
        return View(
            name=view.name,
            sql_table_name=view.sql_table_name,
            derived_table=view.derived_table,
            fields=list(all_fields.values()),
            extends=view.extends,
            source=view.source,
            label=view.label,
            description=view.description,
            suggestions=view.suggestions,
        )

    def _expand_dimension_groups(self, view: View) -> View:
        """Expand dimension_group fields into individual timeframe fields.

        Looker auto-generates fields for each timeframe in a dimension_group.
        For example, dimension_group: start with timeframes: [raw, date, week]
        creates: start_raw, start_date, start_week.

        Args:
            view: View to expand

        Returns:
            View with expanded fields
        """
        expanded_fields = []

        for field in view.fields:
            # Always keep the original field
            expanded_fields.append(field)

            # Expand dimension_group fields
            if field.field_type == FieldType.DIMENSION_GROUP and field.timeframes:
                for timeframe in field.timeframes:
                    # Generate field name: {dimension_group_name}_{timeframe}
                    generated_name = f"{field.name}_{timeframe}"

                    # Determine field type based on timeframe
                    field_type_str = self._get_timeframe_type(timeframe)

                    expanded_fields.append(
                        Field(
                            name=generated_name,
                            field_type=FieldType.DIMENSION,
                            type=field_type_str,
                            sql=None,  # Auto-generated by Looker
                            source=field.source,
                            hidden=field.hidden,
                            label=field.label,
                            description=f"Auto-generated from dimension_group {field.name}",
                        )
                    )

        # Return new view with expanded fields
        return View(
            name=view.name,
            sql_table_name=view.sql_table_name,
            derived_table=view.derived_table,
            fields=expanded_fields,
            extends=view.extends,
            source=view.source,
            label=view.label,
            description=view.description,
            suggestions=view.suggestions,
        )

    def _get_timeframe_type(self, timeframe: str) -> str:
        """Map Looker timeframe to field type.

        Args:
            timeframe: Timeframe string (raw, date, time, week, etc.)

        Returns:
            Field type string
        """
        # Time-based timeframes
        if timeframe in [
            "time",
            "hour",
            "hour_of_day",
            "minute",
            "second",
            "millisecond",
            "microsecond",
            "time_of_day",
        ]:
            return "time"

        # Raw timestamps
        if timeframe == "raw":
            return "datetime"

        # Everything else is date-based
        # (date, week, month, quarter, year, day_of_week, etc.)
        return "date"

    def _apply_refinements(self) -> None:
        """Merge refinement views with their base views.

        Refinements (views starting with '+') are Looker's way of inline view overrides.
        They should be merged with their base views, with refinement fields overriding
        base fields when there's a conflict.

        This method:
        1. Finds all refinement views (+view_name)
        2. Merges their fields into base views (refinement overrides)
        3. Removes refinement views from the views dict
        """
        # Find all refinement views
        refinement_views = [name for name in self.views.keys() if name.startswith("+")]

        for refinement_name in refinement_views:
            # Extract base view name (remove '+' prefix)
            base_name = refinement_name[1:]

            # Check if base view exists
            if base_name not in self.views:
                # Base view doesn't exist - this is likely an error in the LookML
                # but we'll skip it gracefully
                continue

            refinement_view = self.views[refinement_name]
            base_view = self.views[base_name]

            # Merge fields: start with base, then override with refinement
            merged_fields = {f.name: f for f in base_view.fields}

            # Override with refinement fields
            for field in refinement_view.fields:
                merged_fields[field.name] = field

            # Create updated base view with merged fields
            self.views[base_name] = View(
                name=base_name,
                sql_table_name=refinement_view.sql_table_name or base_view.sql_table_name,
                derived_table=refinement_view.derived_table or base_view.derived_table,
                fields=list(merged_fields.values()),
                extends=base_view.extends,  # Keep base extends
                source=base_view.source,  # Keep base source
                label=refinement_view.label or base_view.label,
                description=refinement_view.description or base_view.description,
                suggestions=refinement_view.suggestions or base_view.suggestions,
            )

            # Remove refinement view (it's been merged)
            del self.views[refinement_name]

    def get_explore_fields(
        self, explore_name: str, include_hidden: bool = False
    ) -> dict[str, list[Field]]:
        """Get all fields available in an explore.

        This resolves:
        - Base view fields
        - Joined view fields
        - Field scoping (if defined)
        - Hidden fields (optionally)

        Args:
            explore_name: Name of explore
            include_hidden: Include hidden fields

        Returns:
            Dict with keys:
            - dimensions: List of dimension fields
            - measures: List of measure fields
            - filters: List of filter fields
            - parameters: List of parameter fields
        """
        explore = self.explores.get(explore_name)
        if not explore:
            return {"dimensions": [], "measures": [], "filters": [], "parameters": []}

        all_fields: dict[str, Field] = {}

        # Get base view fields
        base_view_name = explore.get_base_view_name()
        base_view = self.get_view(base_view_name, resolve_extends=True)
        if base_view:
            for field in base_view.fields:
                qualified_name = field.get_qualified_name(base_view.name)
                all_fields[qualified_name] = field

        # Get joined view fields
        for join in explore.joins:
            # Determine which view to use (join.from_view or join.name)
            joined_view_name = join.from_view or join.name
            joined_view = self.get_view(joined_view_name, resolve_extends=True)

            if joined_view:
                # Check if join has field scoping
                if join.fields:
                    # Only include specified fields
                    for field_ref in join.fields:
                        # field_ref could be "view.field" or just "field"
                        parts = field_ref.split(".")
                        field_name = parts[-1] if parts else field_ref

                        field = joined_view.get_field(field_name)
                        if field:
                            qualified_name = field.get_qualified_name(joined_view.name)
                            all_fields[qualified_name] = field
                else:
                    # Include all fields from joined view
                    for field in joined_view.fields:
                        qualified_name = field.get_qualified_name(joined_view.name)
                        all_fields[qualified_name] = field

        # Apply explore-level field scoping if defined
        if explore.has_field_scoping():
            scoped_fields = {}
            for field_ref in explore.fields:
                if field_ref in all_fields:
                    scoped_fields[field_ref] = all_fields[field_ref]
            all_fields = scoped_fields

        # Filter hidden fields if requested
        if not include_hidden:
            all_fields = {k: v for k, v in all_fields.items() if not v.hidden}

        # Group by field type
        result = {"dimensions": [], "measures": [], "filters": [], "parameters": []}

        for field in all_fields.values():
            if field.field_type.value == "dimension" or field.field_type.value == "dimension_group":
                result["dimensions"].append(field)
            elif field.field_type.value == "measure":
                result["measures"].append(field)
            elif field.field_type.value == "filter":
                result["filters"].append(field)
            elif field.field_type.value == "parameter":
                result["parameters"].append(field)

        return result

    def validate_field_reference(
        self,
        ref: FieldReference,
        context_view: Optional[str] = None,
        skip_missing_views: bool = True,
    ) -> Optional[ValidationError]:
        """Validate a field reference exists.

        Args:
            ref: Field reference to validate
            context_view: View context for local references (${field})
            skip_missing_views: If True, skip validation for fields in non-existent views
                              (useful for projects with remote dependencies)

        Returns:
            ValidationError if reference is invalid, None if valid
        """
        # Determine which view to check
        if ref.is_local():
            if not context_view:
                return ValidationError(
                    type="invalid_field_reference",
                    message=f"Local field reference {ref.raw_reference} but no context view",
                    file_path=ref.source.file_path if ref.source else Path("unknown"),
                    line_number=ref.source.line_number if ref.source else None,
                    field_name=ref.field_name,
                )
            view_name = context_view
        else:
            view_name = ref.view_name

        # Check if view exists
        assert view_name
        view = self.get_view(view_name, resolve_extends=True)
        if not view:
            # If skip_missing_views is True, silently skip validation for this reference
            # (the missing view will be reported separately if needed)
            if skip_missing_views:
                return None

            return ValidationError(
                type="missing_view",
                message=f"View '{view_name}' not found (referenced in {ref.raw_reference})",
                file_path=ref.source.file_path if ref.source else Path("unknown"),
                line_number=ref.source.line_number if ref.source else None,
                view_name=view_name,
                field_name=ref.field_name,
            )

        # Check if field exists in view
        if not view.has_field(ref.field_name):
            # If skip_missing_views is True, skip for views that might be incomplete
            # (useful for projects with remote dependencies)
            if skip_missing_views:
                return None

            return ValidationError(
                type="invalid_field_reference",
                message=f"Field '{ref.field_name}' not found in view '{view_name}'",
                file_path=ref.source.file_path if ref.source else Path("unknown"),
                line_number=ref.source.line_number if ref.source else None,
                view_name=view_name,
                field_name=ref.field_name,
            )

        return None

    def validate_view(self, view_name: str) -> list[ValidationError]:
        """Validate all field references in a view.

        Returns:
            List of validation errors (empty if valid)
        """
        view = self.views.get(view_name)
        if not view:
            return [
                ValidationError(
                    type="missing_view",
                    message=f"View '{view_name}' not found",
                    file_path=Path("unknown"),
                )
            ]

        errors: list[ValidationError] = []

        # Validate field SQL references
        for field in view.fields:
            if field.sql:
                refs = self.parser.parser.extract_field_references(field.sql)
                for ref in refs:
                    error = self.validate_field_reference(ref, context_view=view_name)
                    if error:
                        errors.append(error)

        # Validate extends
        for extended_view in view.extends:
            if extended_view not in self.views:
                errors.append(
                    ValidationError(
                        type="missing_view",
                        message=f"Extended view '{extended_view}' not found",
                        file_path=view.source.file_path if view.source else Path("unknown"),
                        line_number=view.source.line_number if view.source else None,
                        view_name=extended_view,
                    )
                )

        return errors

    def validate_explore(self, explore_name: str) -> list[ValidationError]:
        """Validate an explore and its joins.

        Returns:
            List of validation errors (empty if valid)
        """
        explore = self.explores.get(explore_name)
        if not explore:
            return [
                ValidationError(
                    type="missing_explore",
                    message=f"Explore '{explore_name}' not found",
                    file_path=Path("unknown"),
                    explore_name=explore_name,
                )
            ]

        errors: list[ValidationError] = []

        # Validate base view exists
        base_view_name = explore.get_base_view_name()
        if base_view_name not in self.views:
            errors.append(
                ValidationError(
                    type="missing_view",
                    message=f"Base view '{base_view_name}' not found for explore '{explore_name}'",
                    file_path=explore.source.file_path if explore.source else Path("unknown"),
                    line_number=explore.source.line_number if explore.source else None,
                    view_name=base_view_name,
                    explore_name=explore_name,
                )
            )

        # Validate joins
        for join in explore.joins:
            joined_view_name = join.from_view or join.name

            if joined_view_name not in self.views:
                errors.append(
                    ValidationError(
                        type="missing_view",
                        message=f"Joined view '{joined_view_name}' not found in explore '{explore_name}'",
                        file_path=join.source.file_path if join.source else Path("unknown"),
                        line_number=join.source.line_number if join.source else None,
                        view_name=joined_view_name,
                        explore_name=explore_name,
                    )
                )

            # Validate required_joins
            for required_join in join.required_joins:
                if not any(j.name == required_join for j in explore.joins):
                    errors.append(
                        ValidationError(
                            type="invalid_join_reference",
                            message=f"Required join '{required_join}' not found in explore '{explore_name}'",
                            file_path=join.source.file_path if join.source else Path("unknown"),
                            line_number=join.source.line_number if join.source else None,
                            explore_name=explore_name,
                        )
                    )

        # Validate field scoping references
        if explore.has_field_scoping():
            available_fields = self.get_explore_fields(explore_name, include_hidden=True)
            all_field_names = set()
            for field_list in available_fields.values():
                for field in field_list:
                    # Get both qualified and unqualified names
                    all_field_names.add(f"{field.name}")

            for field_ref in explore.fields:
                # Handle wildcards (ALL_FIELDS*, view.*)
                if field_ref == "ALL_FIELDS*" or field_ref.endswith(".*"):
                    # Wildcard - include all available fields, skip validation
                    continue

                # Handle exclusions (-field, -view.field)
                if field_ref.startswith("-"):
                    # Exclusion syntax - removes a field from the set
                    # Skip validation for exclusions as they don't need to exist yet
                    continue

                # Simple check - field should exist in some form
                # More sophisticated checking could parse view.field format
                if "." in field_ref:
                    parts = field_ref.split(".")
                    field_name = parts[-1]
                else:
                    field_name = field_ref

                # Check if any field matches this name
                found = any(
                    field.name == field_name
                    for field_list in available_fields.values()
                    for field in field_list
                )

                if not found:
                    errors.append(
                        ValidationError(
                            type="invalid_field_reference",
                            message=f"Field '{field_ref}' in explore field scoping not found",
                            file_path=explore.source.file_path
                            if explore.source
                            else Path("unknown"),
                            line_number=explore.source.line_number if explore.source else None,
                            field_name=field_ref,
                            explore_name=explore_name,
                        )
                    )

        return errors

    def validate_all(self) -> list[ValidationError]:
        """Validate all views and explores in project.

        Returns:
            List of all validation errors
        """
        errors: list[ValidationError] = []

        for view_name in self.views:
            errors.extend(self.validate_view(view_name))

        for explore_name in self.explores:
            errors.extend(self.validate_explore(explore_name))

        return errors

    def _qualify_node_name(self, node_name: str) -> str | None:
        """Convert a node name to qualified format (type.name).

        Supports:
        - 'name' -> tries 'view.name' and 'explore.name'
        - 'view.name' or 'explore.name' -> returns as-is if exists
        - 'view.name.field.field_name' -> returns as-is if exists
        - 'explore.name.field.view.field_name' -> returns as-is if exists

        Args:
            node_name: Either 'name', 'type.name', or full field path

        Returns:
            Qualified name, or None if not found
        """
        # Already fully qualified (check exact match first)
        if node_name in self.graph:
            return node_name

        # Try view
        qualified_view = f"view.{node_name}"
        if qualified_view in self.graph:
            return qualified_view

        # Try explore
        qualified_explore = f"explore.{node_name}"
        if qualified_explore in self.graph:
            return qualified_explore

        return None

    def get_dependencies(self, node_name: str) -> list[str]:
        """Get all nodes that this node depends on.

        Args:
            node_name: Name of view or explore (accepts 'name' or 'type.name')

        Returns:
            List of qualified dependency names ('type.name' format)
        """
        qualified = self._qualify_node_name(node_name)
        if not qualified:
            return []

        return list(self.graph.successors(qualified))

    def get_dependents(self, node_name: str) -> list[str]:
        """Get all nodes that depend on this node.

        Args:
            node_name: Name of view or explore (accepts 'name' or 'type.name')

        Returns:
            List of qualified dependent names ('type.name' format)
        """
        qualified = self._qualify_node_name(node_name)
        if not qualified:
            return []

        return list(self.graph.predecessors(qualified))

    def get_impact_analysis(self, node_name: str) -> dict[str, Any]:
        """Get impact analysis for changing a node.

        Args:
            node_name: Name of view or explore (accepts 'name' or 'type.name')

        Returns dict with:
        - direct_dependents: Qualified names of nodes directly depending on this
        - transitive_dependents: All qualified names transitively depending on this
        - explores_affected: Qualified names of explores that would be affected
        """
        qualified = self._qualify_node_name(node_name)
        if not qualified:
            return {
                "direct_dependents": [],
                "transitive_dependents": [],
                "explores_affected": [],
            }

        # Get all reachable nodes (transitive closure)
        reachable = nx.ancestors(self.graph, qualified)

        # Get direct dependents
        direct = list(self.graph.predecessors(qualified))

        # Filter explores
        explores = [name for name in reachable if self.graph.nodes[name].get("type") == "explore"]

        return {
            "direct_dependents": direct,
            "transitive_dependents": list(reachable),
            "explores_affected": explores,
        }

    def find_cycles(self) -> list[list[str]]:
        """Find circular dependencies in the project.

        Returns:
            List of cycles (each cycle is a list of qualified node names 'type.name')
        """
        try:
            cycles = list(nx.simple_cycles(self.graph))
            return cycles
        except Exception:
            return []

    def find_orphaned_views(self) -> list[str]:
        """Find views not used by any explore.

        Returns:
            List of orphaned view names
        """
        orphaned = []

        for view_name in self.views:
            # Check if any explore uses this view
            used = False
            for explore in self.explores.values():
                if explore.get_base_view_name() == view_name:
                    used = True
                    break

                for join in explore.joins:
                    if join.name == view_name or join.from_view == view_name:
                        used = True
                        break

                if used:
                    break

            if not used:
                orphaned.append(view_name)

        return orphaned
