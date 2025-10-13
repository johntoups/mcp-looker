"""LookML parsing and analysis utilities."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lkml


@dataclass
class LookMLField:
    """Represents a field in a LookML view."""

    name: str
    type: str  # dimension, measure, dimension_group, etc.
    sql: str | None = None
    description: str | None = None
    hidden: bool = False


@dataclass
class LookMLView:
    """Represents a LookML view."""

    name: str
    sql_table_name: str | None = None
    derived_table: dict[str, Any] | None = None
    fields: list[LookMLField] | None = None
    extends: list[str] | None = None


@dataclass
class LookMLExplore:
    """Represents a LookML explore."""

    name: str
    view_name: str | None = None
    joins: list[dict[str, Any]] | None = None
    fields: list[str] | None = None
    hidden: bool = False


@dataclass
class LookMLModel:
    """Represents a LookML model."""

    name: str
    connection: str | None = None
    explores: list[LookMLExplore] | None = None
    includes: list[str] | None = None


def parse_lookml_file(file_path: Path) -> dict[str, Any]:
    """
    Parse a LookML file into a Python dictionary.

    Args:
        file_path: Path to the .lkml file

    Returns:
        Parsed LookML as a dictionary
    """
    content = file_path.read_text()
    return lkml.load(content)


def extract_views_from_file(file_path: Path) -> list[LookMLView]:
    """
    Extract all views from a LookML file.

    Args:
        file_path: Path to the .lkml or .view.lkml file

    Returns:
        List of LookMLView objects
    """
    parsed = parse_lookml_file(file_path)
    views = []

    if "views" in parsed:
        for view_dict in parsed["views"]:
            fields = []

            # Extract dimensions
            if "dimensions" in view_dict:
                for dim in view_dict["dimensions"]:
                    fields.append(
                        LookMLField(
                            name=dim.get("name", ""),
                            type="dimension",
                            sql=dim.get("sql"),
                            description=dim.get("description"),
                            hidden=dim.get("hidden", False),
                        )
                    )

            # Extract dimension groups
            if "dimension_groups" in view_dict:
                for dim_group in view_dict["dimension_groups"]:
                    fields.append(
                        LookMLField(
                            name=dim_group.get("name", ""),
                            type="dimension_group",
                            sql=dim_group.get("sql"),
                            description=dim_group.get("description"),
                            hidden=dim_group.get("hidden", False),
                        )
                    )

            # Extract measures
            if "measures" in view_dict:
                for measure in view_dict["measures"]:
                    fields.append(
                        LookMLField(
                            name=measure.get("name", ""),
                            type="measure",
                            sql=measure.get("sql"),
                            description=measure.get("description"),
                            hidden=measure.get("hidden", False),
                        )
                    )

            view = LookMLView(
                name=view_dict.get("name", ""),
                sql_table_name=view_dict.get("sql_table_name"),
                derived_table=view_dict.get("derived_table"),
                fields=fields,
                extends=view_dict.get("extends"),
            )
            views.append(view)

    return views


def extract_explores_from_file(file_path: Path) -> list[LookMLExplore]:
    """
    Extract all explores from a LookML model file.

    Args:
        file_path: Path to the .model.lkml file

    Returns:
        List of LookMLExplore objects
    """
    parsed = parse_lookml_file(file_path)
    explores = []

    if "explores" in parsed:
        for explore_dict in parsed["explores"]:
            explore = LookMLExplore(
                name=explore_dict.get("name", ""),
                view_name=explore_dict.get("view_name"),
                joins=explore_dict.get("joins"),
                fields=explore_dict.get("fields"),
                hidden=explore_dict.get("hidden", False),
            )
            explores.append(explore)

    return explores


def extract_model_from_file(file_path: Path) -> LookMLModel | None:
    """
    Extract model information from a LookML model file.

    Args:
        file_path: Path to the .model.lkml file

    Returns:
        LookMLModel object or None if not a valid model file
    """
    parsed = parse_lookml_file(file_path)

    # Model name is typically the filename without extension
    model_name = file_path.stem.replace(".model", "")

    explores = extract_explores_from_file(file_path)

    return LookMLModel(
        name=model_name,
        connection=parsed.get("connection"),
        explores=explores,
        includes=parsed.get("includes"),
    )


def find_field_references(view: LookMLView, field_name: str) -> list[LookMLField]:
    """
    Find all fields that reference a specific field in their SQL.

    Args:
        view: LookMLView to search
        field_name: Field name to search for

    Returns:
        List of fields that reference the given field
    """
    if not view.fields:
        return []

    references = []
    search_term = f"${{{field_name}}}"

    for field in view.fields:
        if field.sql and search_term in field.sql:
            references.append(field)

    return references


def get_all_view_files(project_dir: Path) -> list[Path]:
    """
    Get all LookML view files in a project directory.

    Args:
        project_dir: Project directory to search

    Returns:
        List of paths to view files
    """
    view_files = []

    # Look for .view.lkml files
    view_files.extend(project_dir.rglob("*.view.lkml"))

    # Also look for views in .lkml files
    for lkml_file in project_dir.rglob("*.lkml"):
        # Skip model files
        if ".model.lkml" not in str(lkml_file):
            try:
                parsed = parse_lookml_file(lkml_file)
                if "views" in parsed:
                    view_files.append(lkml_file)
            except Exception:
                # Skip files that can't be parsed
                continue

    return view_files


def get_all_model_files(project_dir: Path) -> list[Path]:
    """
    Get all LookML model files in a project directory.

    Args:
        project_dir: Project directory to search

    Returns:
        List of paths to model files
    """
    return list(project_dir.rglob("*.model.lkml"))


def find_view_usage_in_explores(
    model_files: list[Path], view_name: str
) -> list[tuple[str, LookMLExplore]]:
    """
    Find all explores that use a specific view.

    Args:
        model_files: List of model file paths to search
        view_name: View name to search for

    Returns:
        List of tuples (model_name, explore) where the view is used
    """
    usage = []

    for model_file in model_files:
        try:
            model = extract_model_from_file(model_file)
            if not model or not model.explores:
                continue

            for explore in model.explores:
                # Check if explore uses this view directly
                if explore.view_name == view_name or explore.name == view_name:
                    usage.append((model.name, explore))
                    continue

                # Check if view is used in joins
                if explore.joins:
                    for join in explore.joins:
                        if join.get("from") == view_name or join.get("name") == view_name:
                            usage.append((model.name, explore))
                            break

        except Exception:
            # Skip files that can't be parsed
            continue

    return usage


def get_view_dependencies(view: LookMLView, all_views: dict[str, LookMLView]) -> list[str]:
    """
    Get all views that a view depends on (via ${view_name.field_name} references).

    Args:
        view: LookMLView to analyze
        all_views: Dictionary mapping view names to LookMLView objects

    Returns:
        List of view names that this view depends on
    """
    dependencies = set()

    if not view.fields:
        return []

    for field in view.fields:
        if not field.sql:
            continue

        # Look for ${view_name.field_name} patterns
        import re

        pattern = r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\}"
        matches = re.findall(pattern, field.sql)

        for view_ref, _ in matches:
            if view_ref in all_views and view_ref != view.name:
                dependencies.add(view_ref)

    # Also check extends
    if view.extends:
        dependencies.update(view.extends)

    return sorted(dependencies)
