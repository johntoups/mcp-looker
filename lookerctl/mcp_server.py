"""MCP (Model Context Protocol) Server for Looker CLI.

This module provides an MCP server that exposes Looker CLI functionality as tools
for AI agents. The server wraps the underlying command functions and handles
LookerClient initialization automatically.

IMPORTANT CONVENTIONS FOR AI AGENTS:
- Explore references use format: "model.explore_name" (e.g., "analytics.users")
- Node references support: "name" or "type.name" (e.g., "order_view" or "view.order_view")
- Field references use format: "view_name.field_name" (e.g., "users.count")
"""

from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from lookerctl.commands.analyze import (
    analyze_all_usage,
    analyze_specific_dashboards,
    find_dashboards_using_explore,
    find_unused_explores,
    get_explore_fields,
    get_folder_dependencies,
    get_folder_inventory,
    get_folder_performance,
    list_all_explores,
    list_all_folders,
    trace_field_usage,
)
from lookerctl.commands.deps import (
    analyze_impact,
    build_dependency_graph,
    find_circular_dependencies,
    get_dependency_tree,
    get_orphaned_views,
    get_statistics,
)
from lookerctl.commands.export import (
    export_all_content,
    export_all_dashboards,
    export_all_lookml,
    export_all_looks,
    export_project_files,
    sync_project_from_git,
    validate_local_changes,
)
from lookerctl.commands.session import (
    checkout_git_branch,
    create_dev_branch,
    get_current_workspace,
    get_project_git_status,
    reset_to_remote,
    switch_to_workspace,
    sync_with_local_git,
)
from lookerctl.commands.test import (
    compare_to_baseline,
    create_baseline,
    create_golden_test,
    get_rendered_sql,
    run_all_golden_tests,
    run_golden_test,
    run_query_and_capture,
)
from lookerctl.core.client import LookerClient
from lookerctl.core.config import verify_env_vars
from lookerctl.core.session_storage import get_preferred_workspace

# Initialize MCP server
mcp = FastMCP("Looker")


# ============================================================================
# Helper Functions
# ============================================================================


def _ensure_env_vars() -> None:
    """Ensure required environment variables are set."""
    verify_env_vars()


def _serialize_result(result: Any) -> Any:
    """
    Serialize result for JSON output.

    Converts Path objects to strings and handles other non-serializable types.
    """
    if isinstance(result, Path):
        return str(result)
    elif isinstance(result, dict):
        return {k: _serialize_result(v) for k, v in result.items()}
    elif isinstance(result, (list, tuple)):
        return [_serialize_result(item) for item in result]
    elif isinstance(result, set):
        return list(result)
    else:
        return result


# ============================================================================
# Export Tools
# ============================================================================


@mcp.tool()
def export_project(
    project_id: str,
    output_dir: str = "./looker_export",
    git_branch: Optional[str] = None,
) -> dict[str, Any]:
    """
    Export all LookML files from a Looker project.

    This downloads all files from the Looker project via the API and saves them
    to a local directory. Useful for backing up projects, analyzing code locally,
    or setting up local development workflows.

    Args:
        project_id: Project ID to export (e.g., "my-project", "analytics")
        output_dir: Directory to export files to (default: ./looker_export)
        git_branch: Optional git branch to export from

    Returns:
        Dictionary with export statistics including:
        - files_exported: Number of files successfully exported
        - total_size: Total size in bytes
        - errors: List of any errors encountered

    Example:
        export_project("hub", "/tmp/looker_export")
        export_project("spoke_prod", "/tmp/spoke", git_branch="dev-branch")
    """
    _ensure_env_vars()

    with LookerClient() as client:
        stats = export_project_files(client, project_id, Path(output_dir), git_branch)

    return _serialize_result(stats)


@mcp.tool()
def export_all_projects(output_dir: str = "./looker_export") -> dict[str, Any]:
    """
    Export LookML files from all Looker projects.

    Iterates through all projects in the Looker instance and exports each one
    to a subdirectory named after the project ID.

    Args:
        output_dir: Base directory for exported files (default: ./looker_export)
                   Projects will be exported to: output_dir/{project_id}/

    Returns:
        Dictionary with overall statistics including:
        - projects_exported: Number of projects successfully exported
        - total_files: Total number of files exported across all projects
        - total_size: Total size in bytes
        - errors: List of any errors encountered

    Example:
        export_all_projects("/tmp/all_projects")
    """
    _ensure_env_vars()

    with LookerClient() as client:
        stats = export_all_lookml(client, Path(output_dir))

    return _serialize_result(stats)


@mcp.tool()
def sync_project(
    project_id: str,
    git_branch: Optional[str] = None,
) -> dict[str, Any]:
    """
    Sync a Looker project from its git repository.

    This pulls the latest changes from the git remote into the Looker project.
    Requires dev workspace. Useful for keeping Looker in sync with git after
    external commits.

    IMPORTANT: This modifies project state and automatically switches to dev workspace.

    Args:
        project_id: Project ID to sync (e.g., "my-project", "analytics")
        git_branch: Optional git branch to sync to

    Returns:
        Dictionary with:
        - success: Boolean indicating if sync succeeded
        - message: Success or error message
        - branch: The branch that was synced (if specified)

    Example:
        sync_project("hub")
        sync_project("spoke_prod", git_branch="master")
    """
    _ensure_env_vars()

    with LookerClient() as client:
        result = sync_project_from_git(client, project_id, git_branch)

    return result


@mcp.tool()
def validate_local(
    project_id: str,
    local_dir: str,
) -> dict[str, Any]:
    """
    Validate local LookML files by pushing to Looker dev branch and validating.

    This enables a local-first development workflow:
    1. Make changes to LookML files locally
    2. Push to Looker dev branch
    3. Get Looker validation feedback
    4. Iterate

    IMPORTANT: This modifies project state and automatically switches to dev workspace.

    Args:
        project_id: Project ID (e.g., "my-project", "analytics")
        local_dir: Directory containing LookML files to validate

    Returns:
        Dictionary with:
        - files_pushed: Number of files successfully pushed
        - files_failed: Number of files that failed to push
        - errors: List of push errors
        - validation: Validation results with:
          - has_errors: Boolean indicating if validation failed
          - errors: List of validation errors with message, file_path, line, severity

    Example:
        validate_local("hub", "/Users/me/looker_hub")
        validate_local("spoke_prod", "./local_project")
    """
    _ensure_env_vars()

    with LookerClient() as client:
        result = validate_local_changes(client, project_id, Path(local_dir))

    return _serialize_result(result)


@mcp.tool()
def export_dashboards(
    output_dir: str = "./looker_export/dashboards",
    limit: Optional[int] = None,
) -> dict[str, Any]:
    """
    Export all user-defined dashboards (UDDs) as LookML.

    User-defined dashboards are stored in Looker's database (not git)
    and can be exported using the dashboard_lookml() API. This is useful
    for backing up dashboards or converting them to LookML for version control.

    Args:
        output_dir: Output directory for dashboard LookML files
        limit: Optional limit on number of dashboards to export (useful for testing)

    Returns:
        Dictionary with export statistics including:
        - dashboards_exported: Number of dashboards exported
        - total_size: Total size in bytes
        - errors: List of any errors encountered

    Example:
        export_dashboards()
        export_dashboards("/tmp/dashboards", limit=10)
    """
    _ensure_env_vars()

    with LookerClient() as client:
        stats = export_all_dashboards(client, Path(output_dir), limit)

    return _serialize_result(stats)


@mcp.tool()
def export_looks(
    output_dir: str = "./looker_export/looks",
    limit: Optional[int] = None,
) -> dict[str, Any]:
    """
    Export all looks (saved queries) as JSON.

    Looks are saved queries stored in Looker's database. This exports complete
    query definitions including model, view, fields, filters, sorts, and limits.

    Args:
        output_dir: Output directory for look JSON files
        limit: Optional limit on number of looks to export (useful for testing)

    Returns:
        Dictionary with export statistics including:
        - looks_exported: Number of looks exported
        - total_size: Total size in bytes
        - errors: List of any errors encountered

    Example:
        export_looks()
        export_looks("/tmp/looks", limit=50)
    """
    _ensure_env_vars()

    with LookerClient() as client:
        stats = export_all_looks(client, Path(output_dir), limit)

    return _serialize_result(stats)


@mcp.tool()
def export_content(output_dir: str = "./looker_export") -> dict[str, Any]:
    """
    Export all Looker content: dashboards and looks.

    This is a convenience function that exports both dashboards and looks
    in a single operation.

    Note: LookML project files (models, views, explores) should be managed
    via git or use export_project/export_all_projects.

    Args:
        output_dir: Base directory for exported content
                   Dashboards: output_dir/dashboards/
                   Looks: output_dir/looks/

    Returns:
        Dictionary with:
        - dashboards_exported: Number of dashboards exported
        - looks_exported: Number of looks exported
        - errors: List of any errors encountered

    Example:
        export_content("/tmp/looker_backup")
    """
    _ensure_env_vars()

    with LookerClient() as client:
        stats = export_all_content(client, Path(output_dir))

    return _serialize_result(stats)


# ============================================================================
# Analysis Tools
# ============================================================================


@mcp.tool()
def analyze_usage() -> dict[str, Any]:
    """
    Analyze explore and field usage across all dashboards and looks.

    This provides comprehensive usage analysis showing which explores and fields
    are actively used in content. Useful for:
    - Identifying unused explores/fields
    - Understanding which parts of your data model are most valuable
    - Planning deprecations or refactoring
    - Optimizing performance by focusing on high-usage areas

    Returns:
        Dictionary with:
        - usage_map: Nested dict of {explore_key: {field: [locations]}}
                    where explore_key is "model.explore" format
        - dashboard_stats: Statistics about dashboard analysis
        - look_stats: Statistics about look analysis
        - total_explores: Total number of explores found in use

    Example usage:
        result = analyze_usage()
        # See which fields are used in hub.users explore:
        hub_users_fields = result["usage_map"].get("hub.users", {})
        # Find all locations using a specific field:
        count_usage = hub_users_fields.get("users.count", [])
    """
    _ensure_env_vars()

    with LookerClient() as client:
        analysis = analyze_all_usage(client)

    return _serialize_result(analysis)


@mcp.tool()
def find_unused_content() -> dict[str, Any]:
    """
    Find explores that are not used in any dashboards or looks.

    This helps identify potentially obsolete explores that could be:
    - Deprecated
    - Documented as low-priority
    - Removed to simplify the data model

    Returns:
        Dictionary with:
        - unused_explores: List of explore keys (format: "model.explore")
        - total_unused: Count of unused explores
        - total_explores: Total number of explores in the instance

    Example:
        result = find_unused_content()
        if result["unused_explores"]:
            print(f"Found {result['total_unused']} unused explores")
            for explore in result["unused_explores"]:
                print(f"  - {explore}")
    """
    _ensure_env_vars()

    with LookerClient() as client:
        analysis = analyze_all_usage(client)
        unused = find_unused_explores(client, analysis)

    return {
        "unused_explores": unused,
        "total_unused": len(unused),
        "total_explores": analysis["total_explores"],
    }


@mcp.tool()
def analyze_explore_usage(
    explore_name: str,
    model: Optional[str] = None,
) -> dict[str, Any]:
    """
    Analyze usage of a specific explore in dashboards and looks (known accounts only).

    IMPORTANT: Only analyzes content in folders belonging to the known folder
    names. Shows all fields from the explore that are in use and where
    they're used in known folders.

    Useful for understanding the impact of changing an explore on specific folders.

    Args:
        explore_name: Explore name. Can be:
                     - "explore_name" (requires model parameter)
                     - "model.explore_name" (full qualified format)
        model: Model name (optional if explore_name is fully qualified)

    Returns:
        Dictionary with:
        - explore_key: The full "model.explore" key
        - fields: Dict of {field_name: [locations]} showing where each field is used
        - total_fields: Number of unique fields in use
        - total_locations: Total number of locations using this explore

    Example:
        # Using full qualified format:
        analyze_explore_usage("hub.users")

        # Using separate model parameter:
        analyze_explore_usage("users", model="hub")

    Note: If the explore is not found in usage analysis, it may not be used
    in known accounts or may not exist in the instance.
    """
    _ensure_env_vars()

    # Parse explore name
    if "." in explore_name:
        model_name, explore = explore_name.split(".", 1)
    elif model:
        model_name = model
        explore = explore_name
    else:
        return {
            "error": "Please specify model either in explore_name (model.explore) or with model parameter"
        }

    explore_key = f"{model_name}.{explore}"

    with LookerClient() as client:
        analysis = analyze_all_usage(client)

        if explore_key not in analysis["usage_map"]:
            return {
                "explore_key": explore_key,
                "error": f"No usage found for {explore_key}",
                "note": "This explore is either not used or does not exist",
            }

        fields = analysis["usage_map"][explore_key]

        # Convert sets to lists for serialization
        fields_serializable = {field: list(locations) for field, locations in fields.items()}

        return {
            "explore_key": explore_key,
            "fields": fields_serializable,
            "total_fields": len(fields),
            "total_locations": sum(len(locations) for locations in fields.values()),
        }


@mcp.tool()
def analyze_dashboards(dashboard_ids: list[str]) -> dict[str, Any]:
    """
    Analyze explore and field usage for specific dashboard(s).

    Fast alternative to analyze_usage - only fetches the dashboards you specify
    instead of all 15K+. Perfect for targeted analysis when optimizing LookML.

    Args:
        dashboard_ids: List of dashboard IDs to analyze (e.g., ["123", "456", "789"])

    Returns:
        Dictionary with:
        - usage_map: Nested dict of {explore_key: {field: [locations]}}
        - stats: Statistics about analysis (dashboards analyzed, explores found, errors)

    Example:
        # Analyze single dashboard
        analyze_dashboards(["123"])

        # Analyze multiple dashboards
        analyze_dashboards(["123", "456", "789"])
    """
    _ensure_env_vars()

    with LookerClient() as client:
        result = analyze_specific_dashboards(client, dashboard_ids)

    return _serialize_result(result)


@mcp.tool()
def find_dashboards_with_explore(explore_key: str) -> dict[str, Any]:
    """
    Find all dashboards that use a specific explore (metadata only, fast).

    This only fetches dashboard IDs and titles, not full details, making it
    very fast even with 15K+ dashboards. Use this to identify candidates
    before doing deep analysis with analyze_dashboards.

    Args:
        explore_key: Explore key in "model.explore" format (e.g., "hub.CE_aws")

    Returns:
        Dictionary with:
        - dashboards: List of {id, title} dicts for matching dashboards
        - total_dashboards_checked: Total dashboards examined
        - total_matches: Number of dashboards using this explore

    Example:
        # Find all dashboards using a specific explore
        result = find_dashboards_with_explore("hub.CE_aws")

        # Then analyze those specific dashboards
        dashboard_ids = [d["id"] for d in result["dashboards"]]
        analyze_dashboards(dashboard_ids)
    """
    _ensure_env_vars()

    with LookerClient() as client:
        result = find_dashboards_using_explore(client, explore_key)

    return _serialize_result(result)


@mcp.tool()
def trace_field(field_name: str) -> dict[str, Any]:
    """
    Trace usage of a specific field across all dashboards and looks.

    Surgical alternative to analyze_usage - only tracks one field instead of
    analyzing everything. Much faster when you need to understand where a
    specific field is used before making changes.

    Args:
        field_name: Field name to trace in "view.field" format
                   (e.g., "aws_cost.total_cost", "users.count")

    Returns:
        Dictionary with:
        - field_name: The field being traced
        - dashboards: List of {id, title, explores, query_count} using this field
        - looks: List of {id, title, explore} using this field
        - total_dashboard_usage: Count of dashboards using this field
        - total_look_usage: Count of looks using this field
        - total_usage: Total usage count
        - stats: Analysis statistics

    Example:
        # Find where a field is used before removing it
        result = trace_field("aws_cost.total_cost")

        if result["total_usage"] > 0:
            print(f"Field is used in {result['total_usage']} locations!")
            print(f"Dashboards: {[d['title'] for d in result['dashboards']]}")
    """
    _ensure_env_vars()

    with LookerClient() as client:
        result = trace_field_usage(client, field_name)

    return _serialize_result(result)


@mcp.tool()
def get_explore_schema(model: str, explore: str) -> dict[str, Any]:
    """
    Get the complete schema for an explore including all available fields.

    This queries the Looker API for the actual runtime schema, showing what
    fields are really available (including from joined views). Essential for:
    - Discovering available fields before writing queries
    - Understanding explore structure
    - Generating query specifications
    - Documenting explores

    Args:
        model: Model name (e.g., "my-project", "analytics")
        explore: Explore name (e.g., "users", "deployments")

    Returns:
        Dictionary with:
        - explore: Full "model.explore" key
        - label: Human-readable label
        - description: Explore description
        - fields: Nested dict with:
          - dimensions: List of dimension fields
          - measures: List of measure fields
          - filters: List of filter fields
          - parameters: List of parameter fields
        - field_count: Count of each field type

        Each field includes: name, type, label, description, sql, hidden, view

    Example:
        schema = get_explore_schema("hub", "users")
        # Get all dimension names:
        dimensions = [f["name"] for f in schema["fields"]["dimensions"]]
        # Get all measure names:
        measures = [f["name"] for f in schema["fields"]["measures"]]

    Use this to build queries programmatically:
        schema = get_explore_schema("hub", "users")
        query_fields = dimensions[:5] + measures[:3]
        run_query("hub", "users", fields=query_fields)
    """
    _ensure_env_vars()

    with LookerClient() as client:
        explore_data = get_explore_fields(client, model, explore)

    return _serialize_result(explore_data)


@mcp.tool()
def list_explores() -> dict[str, Any]:
    """
    List all available model.explore combinations in the Looker instance.

    This helps discover what explores exist and their correct names for use
    in queries and analysis. Essential for:
    - Discovering available explores
    - Finding the correct "model.explore" format for queries
    - Understanding the data model structure
    - Generating documentation

    Returns:
        Dictionary with:
        - explores: List of explore dictionaries, each with:
          - model: Model name
          - explore: Explore name
          - key: Full "model.explore" format (use this in other tools)
          - label: Human-readable label
          - description: Explore description
          - hidden: Boolean indicating if explore is hidden
        - total_explores: Count of explores

    Example:
        result = list_explores()
        # Find all explores in the "hub" model:
        hub_explores = [e for e in result["explores"] if e["model"] == "hub"]

        # Get all explore keys for querying:
        explore_keys = [e["key"] for e in result["explores"]]

        # Find a specific explore:
        users_explore = next(e for e in result["explores"] if e["explore"] == "users")
    """
    _ensure_env_vars()

    with LookerClient() as client:
        explores = list_all_explores(client)

    return {
        "explores": explores,
        "total_explores": len(explores),
    }


@mcp.tool()
def list_folders() -> dict[str, Any]:
    """
    List all folders in the Looker instance.

    Folders are used to organize dashboards and looks in Looker. This provides
    a hierarchical view of all folders including their IDs, names, and parent
    relationships. Useful for:
    - Understanding content organization
    - Identifying folder naming patterns
    - Finding folders by name or ID
    - Analyzing folder structure

    Returns:
        Dictionary with:
        - folders: List of folder dictionaries, each with:
          - id: Folder ID
          - name: Folder name
          - parent_id: Parent folder ID (None for root folders)
        - total_folders: Count of folders

    Example:
        result = list_folders()
        # Find all root folders (no parent):
        root_folders = [f for f in result["folders"] if f["parent_id"] is None]

        # Find folders with specific naming pattern:
        account_folders = [f for f in result["folders"] if "account" in f["name"].lower()]

        # Get folder by ID:
        folder = next(f for f in result["folders"] if f["id"] == "123")
    """
    _ensure_env_vars()

    with LookerClient() as client:
        folders = list_all_folders(client)

    return {
        "folders": folders,
        "total_folders": len(folders),
    }


@mcp.tool()
def get_folder_inventory_mcp(folder_name: str) -> dict[str, Any]:
    """
    Get inventory of content for folders matching a specific name.

    IMPORTANT: Folders exist ONLY for users who create custom content. Most users
    consume OOTB dashboards and don't have folders.

    Args:
        folder_name: Folder name or identifier to search for

    Returns:
        Dictionary with:
        - folder_name: The folder name searched
        - users: List of users who create content in these folders
        - folders: List of folders matching the name
        - total_dashboards: Count of dashboards in matching folders
        - total_looks: Count of looks in matching folders
        - error: Error message if no folders found

    Example:
        # Get inventory for folder name:
        inventory = get_folder_inventory_mcp("my-folder-name")

        if "error" not in inventory:
            print(f"Folders have {inventory['total_dashboards']} dashboards")
            print(f"Users: {', '.join(inventory['users'])}")
    """
    _ensure_env_vars()

    with LookerClient() as client:
        result = get_folder_inventory(client, folder_name)

    return _serialize_result(result)


@mcp.tool()
def get_folder_dependencies_mcp(folder_name: str) -> dict[str, Any]:
    """
    Analyze dependencies for folders matching a specific name.

    Shows which explores and fields the folder's dashboards depend on.
    Critical for understanding impact of changes on specific folders.

    Args:
        folder_name: Folder name or identifier to search for

    Returns:
        Dictionary with:
        - folder_name: The folder name searched
        - dashboards_analyzed: Number of dashboards analyzed
        - total_explores: Number of unique explores used
        - total_fields: Total unique fields across all explores
        - explores_used: List of explores with field details, each with:
          - explore: Explore key (format: "model.explore")
          - field_count: Number of fields used from this explore
          - fields: List of field names used
        - error: Error message if no folders found

    Example:
        # Analyze dependencies before making changes:
        deps = get_folder_dependencies_mcp("my-folder-name")

        if "error" not in deps:
            print(f"Folders use {deps['total_explores']} explores")
            for explore_info in deps['explores_used']:
                print(f"  {explore_info['explore']}: {explore_info['field_count']} fields")
    """
    _ensure_env_vars()

    with LookerClient() as client:
        result = get_folder_dependencies(client, folder_name)

    return _serialize_result(result)


@mcp.tool()
def get_folder_performance_mcp(
    folder_name: str,
    slow_threshold_seconds: float = 5.0,
) -> dict[str, Any]:
    """
    Identify dashboards with performance issues for folders matching a name.

    Analyzes query performance for all dashboards in matching folders and
    identifies slow queries that exceed the threshold.

    Args:
        folder_name: Folder name or identifier to search for
        slow_threshold_seconds: Threshold for slow queries in seconds (default: 5.0)

    Returns:
        Dictionary with:
        - folder_name: The folder name searched
        - total_dashboards: Total dashboards in matching folders
        - total_queries_analyzed: Number of queries examined
        - slow_threshold_seconds: The threshold used
        - dashboards_with_slow_queries: Count of dashboards with slow queries
        - total_slow_queries: Total number of slow queries found
        - slow_dashboards: List of dashboards with slow queries, each with:
          - dashboard_id: Dashboard ID
          - title: Dashboard title
          - folder_name: Folder name
          - slow_query_count: Number of slow queries in dashboard
          - avg_runtime: Average runtime of slow queries
          - slow_queries: List of slow query details
        - folders_analyzed: Number of folders analyzed
        - error: Error message if no folders found

    Example:
        # Find performance issues with 5 second threshold:
        perf = get_folder_performance_mcp("my-folder-name")

        if "error" not in perf:
            print(f"Found {perf['dashboards_with_slow_queries']} slow dashboards")
            for dashboard in perf['slow_dashboards']:
                print(f"  {dashboard['title']}: {dashboard['slow_query_count']} slow queries")

        # Use stricter threshold:
        perf = get_folder_performance_mcp("my-folder-name", slow_threshold_seconds=2.0)
    """
    _ensure_env_vars()

    with LookerClient() as client:
        result = get_folder_performance(client, folder_name, slow_threshold_seconds)

    return _serialize_result(result)


# ============================================================================
# Session/Workspace Tools
# ============================================================================


@mcp.tool()
def get_session_info() -> dict[str, Any]:
    """
    Get current session information and workspace preference.

    Shows the current Looker session state and the saved workspace preference
    that persists across CLI invocations.

    Returns:
        Dictionary with:
        - workspace_id: Current workspace ("dev" or "production")
        - preferred_workspace: Saved default workspace preference
        - user_id: Current user ID (if using sudo)

    Example:
        info = get_session_info()
        if info["workspace_id"] != "dev":
            set_workspace("dev")
    """
    _ensure_env_vars()

    with LookerClient() as client:
        sess = client.get_session()
        preferred = get_preferred_workspace()

        return {
            "workspace_id": sess.workspace_id,
            "preferred_workspace": preferred,
            "user_id": sess.sudo_user_id or None,
        }


@mcp.tool()
def get_workspace() -> dict[str, str]:
    """
    Get the current Looker workspace (dev or production).

    Workspaces in Looker:
    - "dev": Development workspace for making changes
    - "production": Production workspace (read-only for most operations)

    Returns:
        Dictionary with workspace_id

    Example:
        result = get_workspace()
        current = result["workspace_id"]
    """
    _ensure_env_vars()

    with LookerClient() as client:
        workspace_id = get_current_workspace(client)

    return {"workspace_id": workspace_id}


@mcp.tool()
def set_workspace(workspace_id: str) -> dict[str, Any]:
    """
    Switch to a different Looker workspace.

    This changes the current session workspace and saves the preference
    to persist across CLI invocations.

    IMPORTANT:
    - Most modification operations require "dev" workspace
    - Production workspace is read-only for safety

    Args:
        workspace_id: Workspace to switch to ("dev" or "production")

    Returns:
        Dictionary with:
        - success: Boolean indicating if switch succeeded
        - message: Success or error message
        - workspace: The workspace that was switched to

    Example:
        # Switch to dev for making changes:
        set_workspace("dev")

        # Switch to production for read-only access:
        set_workspace("production")
    """
    _ensure_env_vars()

    if workspace_id not in ["dev", "production"]:
        return {
            "success": False,
            "message": f"Invalid workspace_id: {workspace_id}. Must be 'dev' or 'production'",
        }

    with LookerClient() as client:
        result = switch_to_workspace(client, workspace_id)

    return result


@mcp.tool()
def get_git_status(project_id: str) -> dict[str, Any]:
    """
    Get git status for a Looker project.

    Shows the current git branch and remote configuration for a project.

    Args:
        project_id: Project ID to check (e.g., "my-project", "analytics")

    Returns:
        Dictionary with:
        - project_id: Project ID
        - project_name: Project name
        - git_remote_url: Git remote repository URL
        - git_branch: Current git branch
        - git_production_branch: Production branch name
        - is_production_branch: Boolean indicating if on production branch

    Example:
        status = get_git_status("hub")
        if status["is_production_branch"]:
            print("Warning: On production branch!")
        print(f"Current branch: {status['git_branch']}")
    """
    _ensure_env_vars()

    with LookerClient() as client:
        status = get_project_git_status(client, project_id)

    return _serialize_result(status)


@mcp.tool()
def checkout_branch(project_id: str, branch: str) -> dict[str, Any]:
    """
    Checkout a git branch in a Looker project.

    Switches the project to a different git branch. Requires dev workspace.

    IMPORTANT: Automatically switches to dev workspace if needed.

    Args:
        project_id: Project ID (e.g., "my-project", "analytics")
        branch: Branch name to checkout (e.g., "master", "dev-feature")

    Returns:
        Dictionary with:
        - success: Boolean indicating if checkout succeeded
        - branch: The branch that was checked out
        - project_id: The project ID
        - error: Error message if failed

    Example:
        checkout_branch("hub", "feature-branch")
        checkout_branch("spoke_prod", "master")
    """
    _ensure_env_vars()

    with LookerClient() as client:
        result = checkout_git_branch(client, project_id, branch)

    return result


@mcp.tool("sync_with_local_git")
def sync_with_local_git_(project_id: str) -> dict[str, Any]:
    """
    Sync Looker project branch with local git repository branch.

    Detects the current git branch in your local repository and checks out
    the corresponding branch in Looker. Useful for keeping Looker in sync
    when working locally.

    IMPORTANT:
    - Must be run from within a git repository
    - Automatically switches to dev workspace
    - Looker project must have a branch matching your local branch

    Args:
        project_id: Project ID (e.g., "my-project", "analytics")

    Returns:
        Dictionary with:
        - success: Boolean indicating if sync succeeded
        - local_branch: The local git branch detected
        - looker_branch: The branch checked out in Looker
        - project_id: The project ID
        - error: Error message if failed

    Example:
        # If you're on branch "feature-x" locally:
        sync_with_local_git("hub")
        # This will checkout "feature-x" in Looker's hub project
    """
    _ensure_env_vars()

    with LookerClient() as client:
        result = sync_with_local_git(client, project_id)

    return result


@mcp.tool()
def create_branch(
    project_id: str,
    branch_name: str,
    from_branch: Optional[str] = None,
) -> dict[str, Any]:
    """
    Create a new development branch in a Looker project.

    Creates a new git branch and checks it out. Requires dev workspace.

    IMPORTANT: Automatically switches to dev workspace if needed.

    Args:
        project_id: Project ID (e.g., "my-project", "analytics")
        branch_name: Name for the new branch (e.g., "feature-new-dashboard")
        from_branch: Branch to create from (defaults to production branch)

    Returns:
        Dictionary with:
        - success: Boolean indicating if creation succeeded
        - branch_name: The branch that was created
        - project_id: The project ID
        - error: Error message if failed

    Example:
        # Create branch from production:
        create_branch("hub", "feature-new-explore")

        # Create branch from specific branch:
        create_branch("hub", "feature-b", from_branch="feature-a")
    """
    _ensure_env_vars()

    with LookerClient() as client:
        result = create_dev_branch(client, project_id, branch_name, from_branch)

    return result


@mcp.tool()
def reset_project_to_remote(project_id: str) -> dict[str, Any]:
    """
    Hard reset Looker project to match git remote.

    Discards any local changes in dev workspace and pulls the latest commit
    from git remote for the current branch. Use this when Looker shows stale
    schema despite git branch being updated.

    IMPORTANT: This will DISCARD all local changes in dev workspace and force
    Looker to match the exact state of the git remote.

    Args:
        project_id: Project ID (e.g., "my-project", "analytics")

    Returns:
        Dictionary with:
        - success: Boolean indicating if reset succeeded
        - branch: The branch that was reset
        - project_id: The project ID
        - message: Response message from Looker API
        - error: Error message if failed

    Example:
        # Reset hub project to match git remote:
        reset_project_to_remote("hub")

        # This is useful when:
        # - Git branch is updated but Looker shows old schema
        # - Need to sync Looker dev workspace with latest remote commits
        # - Want to discard local experiments in Looker
    """
    _ensure_env_vars()

    with LookerClient() as client:
        result = reset_to_remote(client, project_id)

    return result


# ============================================================================
# Project Information Tools
# ============================================================================


@mcp.tool()
def list_projects() -> dict[str, Any]:
    """
    List all Looker projects.

    Returns information about all projects in the Looker instance including
    git configuration.

    Returns:
        Dictionary with:
        - projects: List of project dictionaries, each with:
          - id: Project ID (use this in other tools)
          - name: Project name
          - git_remote_url: Git repository URL
          - git_production_branch_name: Production branch name
        - total_projects: Count of projects

    Example:
        result = list_projects()
        # Find a specific project:
        hub = next(p for p in result["projects"] if p["id"] == "hub")

        # Get all project IDs:
        project_ids = [p["id"] for p in result["projects"]]
    """
    _ensure_env_vars()

    with LookerClient() as client:
        projects = client.get_all_projects()

    # Convert to serializable format
    projects_data = []
    for project in projects:
        projects_data.append(
            {
                "id": project.id,
                "name": project.name,
                "git_remote_url": project.git_remote_url,
                "git_production_branch_name": project.git_production_branch_name,
            }
        )

    return {
        "projects": projects_data,
        "total_projects": len(projects_data),
    }


@mcp.tool()
def validate_project(project_id: str) -> dict[str, Any]:
    """
    Validate a LookML project in Looker.

    Runs Looker's built-in validation on a project to check for:
    - Syntax errors
    - Reference errors (missing views, fields, etc.)
    - Type mismatches
    - Other LookML issues

    Args:
        project_id: Project ID to validate (e.g., "my-project", "analytics")

    Returns:
        Dictionary with:
        - has_errors: Boolean indicating if validation failed
        - errors: List of error dictionaries with:
          - message: Error message
          - file_path: File where error occurred
          - line_number: Line number of error
          - severity: Error severity level

    Example:
        result = validate_project("hub")
        if result["has_errors"]:
            for error in result["errors"]:
                print(f"{error['file_path']}:{error['line_number']}: {error['message']}")
        else:
            print("Validation passed!")
    """
    _ensure_env_vars()

    with LookerClient() as client:
        result = client.validate_project(project_id)

    # Convert to serializable format
    validation_result = {
        "has_errors": bool(result.errors),
        "errors": [],
    }

    if result.errors:
        for error in result.errors:
            validation_result["errors"].append(
                {
                    "message": error.message,
                    "file_path": getattr(error, "file_path", None),
                    "line_number": getattr(error, "line_number", None),
                    "severity": getattr(error, "severity", None),
                }
            )

    return validation_result


# ============================================================================
# Query Testing Tools
# ============================================================================


@mcp.tool()
def run_query(
    model: str,
    explore: str,
    fields: list[str],
    filters: Optional[dict[str, str]] = None,
    sorts: Optional[list[str]] = None,
    limit: int = 500,
) -> dict[str, Any]:
    """
    Run a query against a Looker explore and capture results.

    This is useful for:
    - Testing queries
    - Creating baselines for comparison
    - Debugging explore behavior
    - Validating field availability

    Args:
        model: Model name (e.g., "my-project", "analytics")
        explore: Explore name (e.g., "users", "deployments")
        fields: List of field names (e.g., ["users.count", "users.city"])
                Use format "view_name.field_name"
        filters: Optional dictionary of filters
                Format: {"field_name": "filter_expression"}
                Example: {"users.state": "California", "users.age": ">18"}
        sorts: Optional list of sort specifications
              Format: ["field_name desc"] or ["field_name asc"]
              Example: ["users.count desc", "users.city asc"]
        limit: Row limit (default: 500, max depends on Looker settings)

    Returns:
        Dictionary with:
        - explore: Full "model.explore" key
        - query: The query specification that was run
        - results: Query results as list of dictionaries
        - row_count: Number of rows returned
        - performance: Dict with runtime_seconds and status
        - metadata: Dict with created_at and query_id

    Example:
        # Simple count query:
        result = run_query(
            "hub", "users",
            fields=["users.count"],
            limit=1
        )

        # Complex query with filters and sorts:
        result = run_query(
            "hub", "deployments",
            fields=["deployments.count", "deployments.service_name"],
            filters={"deployments.created_date": "7 days"},
            sorts=["deployments.count desc"],
            limit=100
        )

    Note: Use get_explore_schema() to discover available fields before querying.
    """
    _ensure_env_vars()

    query_spec = {
        "fields": fields,
        "filters": filters or {},
        "sorts": sorts or [],
        "limit": str(limit),
    }

    with LookerClient() as client:
        result = run_query_and_capture(client, model, explore, query_spec)

    return _serialize_result(result)


@mcp.tool()
def get_query_sql(
    model: str,
    explore: str,
    fields: list[str],
    filters: Optional[dict[str, str]] = None,
    sorts: Optional[list[str]] = None,
    limit: int = 500,
) -> dict[str, Any]:
    """
    Get the SQL that Looker would generate without executing the query.

    This uses run_inline_query with result_format="sql" to get the rendered SQL
    that Looker would execute. Useful for:
    - Query profiling and optimization
    - Understanding generated SQL
    - Debugging query issues
    - Running dry-run validations in BigQuery

    Args:
        model: Model name (e.g., "my-project", "analytics")
        explore: Explore name (e.g., "users", "deployments")
        fields: List of field names (e.g., ["users.count", "users.city"])
                Use format "view_name.field_name"
        filters: Optional dictionary of filters
                Format: {"field_name": "filter_expression"}
                Example: {"users.state": "California", "users.age": ">18"}
        sorts: Optional list of sort specifications
              Format: ["field_name desc"] or ["field_name asc"]
              Example: ["users.count desc", "users.city asc"]
        limit: Row limit (default: 500)

    Returns:
        Dictionary with:
        - sql: The rendered SQL query as a string
        - model: Model name
        - explore: Explore name
        - query: The query specification that was rendered

    Example:
        # Get SQL for a query:
        result = get_query_sql(
            "hub", "users",
            fields=["users.count", "users.state"],
            filters={"users.created_date": "30 days"},
            limit=1000
        )
        print(result["sql"])

        # Use with BigQuery dry run for cost estimation:
        sql = get_query_sql("hub", "users", fields=["users.count"])["sql"]
        # Then pass to BigQuery MCP for dry run analysis
    """
    _ensure_env_vars()

    with LookerClient() as client:
        result = get_rendered_sql(
            client,
            model,
            explore,
            fields,
            filters=filters,
            sorts=sorts,
            limit=limit,
        )

    return _serialize_result(result)


@mcp.tool()
def create_query_baseline(
    model: str,
    explore: str,
    fields: list[str],
    output_file: str,
    filters: Optional[dict[str, str]] = None,
    sorts: Optional[list[str]] = None,
    limit: int = 500,
) -> dict[str, Any]:
    """
    Create a baseline by running a query and saving results.

    Baselines are used for A/B testing when making changes to explores.
    Workflow:
    1. Create baseline before making changes
    2. Make your LookML changes
    3. Compare new results to baseline to verify behavior

    Args:
        model: Model name (e.g., "hub")
        explore: Explore name (e.g., "users")
        fields: List of field names (format: "view.field")
        output_file: Path to save baseline file (JSON)
        filters: Optional filters dict
        sorts: Optional sorts list
        limit: Row limit (default: 500)

    Returns:
        Dictionary with:
        - explore: Full "model.explore" key
        - query: Query specification
        - results: Complete query results
        - row_count: Number of rows
        - performance: Runtime metrics
        - metadata: Timestamp, git info, query ID

    Example:
        # Create baseline before refactoring:
        baseline = create_query_baseline(
            "hub", "users",
            fields=["users.count", "users.state"],
            output_file="./baselines/users_count.json",
            filters={"users.created_date": "30 days"},
            limit=1000
        )

        # Later, compare to baseline after changes:
        compare_query_baseline(
            "hub", "users",
            baseline_file="./baselines/users_count.json"
        )
    """
    _ensure_env_vars()

    query_spec = {
        "fields": fields,
        "filters": filters or {},
        "sorts": sorts or [],
        "limit": str(limit),
    }

    with LookerClient() as client:
        baseline = create_baseline(client, model, explore, query_spec, Path(output_file))

    return _serialize_result(baseline)


@mcp.tool()
def compare_query_baseline(
    model: str,
    explore: str,
    baseline_file: str,
    numeric_tolerance: float = 0.01,
) -> dict[str, Any]:
    """
    Run query and compare results to baseline.

    Compares current query results against a previously saved baseline to detect
    changes in behavior. Useful for:
    - Verifying refactoring didn't change results
    - A/B testing LookML changes
    - Regression testing

    Args:
        model: Model name (e.g., "hub")
        explore: Explore name (e.g., "users")
        baseline_file: Path to baseline file created with create_query_baseline()
        numeric_tolerance: Tolerance for numeric comparisons (default: 0.01 = 1%)
                          Accounts for rounding differences

    Returns:
        Dictionary with:
        - passed: Boolean indicating if results match baseline
        - baseline: Baseline statistics (row_count, runtime)
        - current: Current query statistics
        - differences: Dict with:
          - row_count_diff: Difference in row counts
          - data_differences: List of data mismatches
        - summary: Human-readable summary message

    Example:
        # After making changes, compare to baseline:
        result = compare_query_baseline(
            "hub", "users",
            baseline_file="./baselines/users_count.json",
            numeric_tolerance=0.001  # Stricter tolerance
        )

        if not result["passed"]:
            print("Results changed!")
            print(result["summary"])
            for diff in result["differences"]["data_differences"]:
                print(f"  - {diff}")
    """
    _ensure_env_vars()

    with LookerClient() as client:
        comparison = compare_to_baseline(
            client,
            model,
            explore,
            Path(baseline_file),
            tolerance={"numeric_tolerance": numeric_tolerance},
        )

    return _serialize_result(comparison)


@mcp.tool()
def create_test(
    test_name: str,
    model: str,
    explore: str,
    fields: list[str],
    expected_row_count: int,
    test_dir: str = "./golden_tests",
    filters: Optional[dict[str, str]] = None,
    sorts: Optional[list[str]] = None,
    limit: int = 500,
    scope: str = "permanent",
) -> dict[str, Any]:
    """
    Create a golden test with expected results.

    Golden tests define expected query behavior that should remain constant.
    Unlike baselines (which capture current state for comparison), golden tests
    define the CORRECT state that must be maintained.

    Use for:
    - Regression testing critical queries
    - Ensuring important metrics stay accurate
    - Preventing accidental breaking changes

    Args:
        test_name: Unique test name (e.g., "users_total_count")
        model: Model name
        explore: Explore name
        fields: List of field names
        expected_row_count: Expected number of rows
        test_dir: Directory to store tests (default: ./golden_tests)
        filters: Optional filters
        sorts: Optional sorts
        limit: Row limit
        scope: Test scope - "permanent" or "feature_branch"
               - permanent: Critical tests that should always pass
               - feature_branch: Tests for specific features

    Returns:
        Dictionary with:
        - success: Boolean indicating if test was created
        - test_file: Path to created test file
        - test_name: Name of the test

    Example:
        # Create a test ensuring users count is always > 0:
        create_test(
            test_name="users_exist",
            model="hub",
            explore="users",
            fields=["users.count"],
            expected_row_count=1,
            scope="permanent"
        )

        # Create a feature-specific test:
        create_test(
            test_name="new_deployment_stats",
            model="hub",
            explore="deployments",
            fields=["deployments.count", "deployments.success_rate"],
            expected_row_count=1,
            filters={"deployments.created_date": "7 days"},
            scope="feature_branch"
        )
    """
    _ensure_env_vars()

    # Parse explore (if in model.explore format)
    if "." in explore:
        model_name, explore_name = explore.split(".", 1)
    else:
        model_name = model
        explore_name = explore

    query_spec = {
        "fields": fields,
        "filters": filters or {},
        "sorts": sorts or [],
        "limit": str(limit),
    }

    expected = {
        "row_count": expected_row_count,
    }

    test_file = create_golden_test(
        test_name, model_name, explore_name, query_spec, expected, Path(test_dir), scope
    )

    return {
        "success": True,
        "test_file": str(test_file),
        "test_name": test_name,
    }


@mcp.tool()
def run_test(
    test_name: Optional[str] = None,
    test_dir: str = "./golden_tests",
) -> dict[str, Any]:
    """
    Run golden tests.

    Executes one or all golden tests and compares results to expected values.

    Args:
        test_name: Optional specific test to run (without .json extension)
                  If not provided, runs all tests in test_dir
        test_dir: Directory containing test files (default: ./golden_tests)

    Returns:
        If running single test:
        - Dictionary with:
          - passed: Boolean indicating if test passed
          - test_name: Name of test
          - actual_row_count: Actual rows returned
          - expected_row_count: Expected rows
          - error: Error message if failed

        If running all tests:
        - Dictionary with:
          - total: Total tests run
          - passed: Number of tests that passed
          - failed: Number of tests that failed
          - results: List of individual test results

    Example:
        # Run specific test:
        result = run_test("users_exist")
        if not result["passed"]:
            print(f"Test failed: {result['error']}")

        # Run all tests:
        results = run_test()
        print(f"Passed: {results['passed']}/{results['total']}")
        for test in results["results"]:
            if not test["passed"]:
                print(f"Failed: {test['test_name']}")
    """
    _ensure_env_vars()

    with LookerClient() as client:
        if test_name:
            # Run specific test
            test_file = Path(test_dir) / f"{test_name}.json"
            result = run_golden_test(client, test_file)
            return _serialize_result(result)
        else:
            # Run all tests
            summary = run_all_golden_tests(client, Path(test_dir))
            return _serialize_result(summary)


# ============================================================================
# Dependency Analysis Tools
# ============================================================================


@mcp.tool()
def analyze_dependencies(
    project_dir: str,
    include_fields: bool = False,
) -> dict[str, Any]:
    """
    Build and analyze the dependency graph for a LookML project.

    This analyzes local LookML files to understand dependencies between
    views, explores, and optionally fields. Useful for:
    - Understanding project structure
    - Finding complex dependency chains
    - Planning refactoring
    - Identifying tightly coupled components

    Args:
        project_dir: Path to LookML project directory (local files)
        include_fields: Whether to include field-level dependencies
                       (default: False, as field graphs can be very large)

    Returns:
        Dictionary with dependency graph statistics:
        - total_nodes: Total nodes in graph
        - total_edges: Total edges (dependencies)
        - total_views: Number of view nodes
        - total_explores: Number of explore nodes
        - avg_dependencies: Average dependencies per node
        - avg_dependents: Average dependents per node

    Example:
        stats = analyze_dependencies("/path/to/looker_hub")
        print(f"Project has {stats['total_views']} views")
        print(f"Average dependencies: {stats['avg_dependencies']:.1f}")

    Note: This works on local files, no API connection needed.
    """
    graph = build_dependency_graph(Path(project_dir), include_fields=include_fields)
    stats = get_statistics(graph)

    return _serialize_result(stats)


@mcp.tool("get_dependency_tree")
def get_dependency_tree_(
    project_dir: str,
    node_name: str,
    max_depth: int = 5,
    include_fields: bool = False,
) -> dict[str, Any]:
    """
    Get dependency tree for a view, explore, or field.

    Shows what a given node depends on, recursively up to max_depth.
    Useful for understanding:
    - What views an explore uses
    - What views a view extends from
    - Field-level dependencies (with include_fields=True)

    Args:
        project_dir: Path to LookML project directory
        node_name: Node to analyze. Accepts:
                  - "view_name" (will try to qualify as "view.view_name")
                  - "view.view_name" (explicit)
                  - "explore.explore_name"
                  - "view.view_name.field.field_name" (with include_fields)
        max_depth: Maximum depth to traverse (default: 5)
        include_fields: Include field-level nodes (default: False)

    Returns:
        Dictionary with nested dependency tree:
        - node: Node name
        - type: Node type (view, explore, field)
        - dependencies: List of dependency subtrees (recursive)

    Example:
        # See what views an explore uses:
        tree = get_dependency_tree(
            "./looker_hub",
            "explore.users",
            max_depth=3
        )

        # Can also use short form (will auto-qualify):
        tree = get_dependency_tree("./looker_hub", "users")

    Note: This works on local files, no API connection needed.
    """
    graph = build_dependency_graph(Path(project_dir), include_fields=include_fields)
    tree = get_dependency_tree(graph, node_name, max_depth)

    return _serialize_result(tree)


@mcp.tool()
def find_orphaned_views(project_dir: str) -> dict[str, Any]:
    """
    Find views that are not used by any explores in the project.

    Orphaned views are:
    - Views that exist but aren't referenced by explores
    - Potentially unused code
    - Candidates for cleanup or documentation

    Note: A view might be "orphaned" but still used:
    - As a base for other views (via extends)
    - In SQL references
    - This tool only checks explore usage

    Args:
        project_dir: Path to LookML project directory

    Returns:
        Dictionary with:
        - orphaned_views: List of view names (format: "view.view_name")
        - total_orphaned: Count of orphaned views

    Example:
        result = find_orphaned_views("./looker_hub")
        if result["orphaned_views"]:
            print(f"Found {result['total_orphaned']} orphaned views:")
            for view in result["orphaned_views"]:
                print(f"  - {view}")

    Note: This works on local files, no API connection needed.
    """
    graph = build_dependency_graph(Path(project_dir))
    orphaned = get_orphaned_views(graph)

    return {
        "orphaned_views": orphaned,
        "total_orphaned": len(orphaned),
    }


@mcp.tool()
def find_circular_deps(project_dir: str) -> dict[str, Any]:
    """
    Find circular dependencies in a LookML project.

    Circular dependencies occur when:
    - View A depends on View B, and View B depends on View A
    - Can cause issues with LookML compilation
    - Should generally be avoided or carefully managed

    Args:
        project_dir: Path to LookML project directory

    Returns:
        Dictionary with:
        - circular_dependencies: List of cycles
          Each cycle is a list of node names forming the circle
        - total_cycles: Count of circular dependencies found

    Example:
        result = find_circular_deps("./looker_hub")
        if result["circular_dependencies"]:
            print(f"Found {result['total_cycles']} circular dependencies!")
            for cycle in result["circular_dependencies"]:
                print(f"  Cycle: {' → '.join(cycle + [cycle[0]])}")

    Note: This works on local files, no API connection needed.
    """
    graph = build_dependency_graph(Path(project_dir))
    cycles = find_circular_dependencies(graph)

    return {
        "circular_dependencies": cycles,
        "total_cycles": len(cycles),
    }


@mcp.tool()
def analyze_change_impact(
    project_dir: str,
    node_name: str,
    include_fields: bool = False,
) -> dict[str, Any]:
    """
    Analyze the impact of changing or removing a view, explore, or field.

    Shows what would be affected if you modify or delete a specific element.
    Essential for:
    - Planning refactoring
    - Assessing risk of changes
    - Understanding dependencies
    - Preventing breaking changes

    Args:
        project_dir: Path to LookML project directory
        node_name: Node to analyze. Accepts:
                  - "view_name" (will qualify as "view.view_name")
                  - "view.view_name"
                  - "explore.explore_name"
                  - "view.view_name.field.field_name" (with include_fields)
        include_fields: Include field-level impact (default: False)

    Returns:
        Dictionary with:
        - node: Node being analyzed
        - total_affected: Total number of nodes affected
        - affected_explores: List of explores that would be affected
        - affected_views: List of views that would be affected
        - direct_dependents: Nodes directly depending on this node

    Example:
        # Before removing a view, check impact:
        impact = analyze_change_impact("./looker_hub", "view.old_users")
        if impact["affected_explores"]:
            print(f"Cannot remove! Used by {len(impact['affected_explores'])} explores:")
            for explore in impact["affected_explores"]:
                print(f"  - {explore}")

        # Can use short form:
        impact = analyze_change_impact("./looker_hub", "old_users")

    Note: This works on local files, no API connection needed.
    """
    graph = build_dependency_graph(Path(project_dir), include_fields=include_fields)
    analysis = analyze_impact(graph, node_name)

    return _serialize_result(analysis)


# ============================================================================
# Cache Management Tools
# ============================================================================


@mcp.tool()
def get_cache_stats() -> dict[str, Any]:
    """
    Get API cache statistics.

    Returns:
        Dictionary with:
        - total_entries: Total number of cache entries
        - active_entries: Non-expired entries
        - expired_entries: Expired entries
        - total_hits: Total cache hits across all entries
        - db_size_mb: Database size in megabytes
        - endpoints: Dictionary of endpoint names to entry counts

    Example:
        stats = get_cache_stats()
        print(f"Cache has {stats['active_entries']} active entries")
        print(f"Total cache hits: {stats['total_hits']}")
        print(f"DB size: {stats['db_size_mb']:.2f} MB")

    Note: Cache is critical for performance with 15K+ dashboards.
    """
    _ensure_env_vars()

    with LookerClient() as client:
        stats = client.get_cache_stats()
        if not stats:
            return {"error": "Cache is disabled"}

        return _serialize_result(stats)


@mcp.tool()
def clear_cache(endpoint: Optional[str] = None) -> dict[str, Any]:
    """
    Clear cache entries.

    Args:
        endpoint: Specific endpoint to clear (all if None)
                 Valid endpoints: "all_dashboards", "all_looks", "dashboard",
                 "query", "dashboard_lookml"

    Returns:
        Dictionary with:
        - deleted: Number of entries deleted
        - endpoint: Endpoint cleared (or "all")

    Examples:
        # Clear all cache
        clear_cache()

        # Clear specific endpoint
        clear_cache("dashboard")
        clear_cache("query")

    Note: Use clear_cache_by_id() to clear specific resource IDs.
    """
    _ensure_env_vars()

    with LookerClient() as client:
        deleted = client.invalidate_cache(endpoint=endpoint)

        return {
            "deleted": deleted,
            "endpoint": endpoint or "all",
        }


@mcp.tool()
def clear_cache_by_id(
    dashboard_id: Optional[str] = None,
    query_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Clear cache for specific resource IDs.

    This clears all cached variants (different field sets) of a resource.

    Args:
        dashboard_id: Dashboard ID to clear
        query_id: Query ID to clear

    Returns:
        Dictionary with:
        - deleted: Number of entries deleted
        - resources_cleared: List of resource IDs cleared

    Examples:
        # Clear specific dashboard (all field variants)
        clear_cache_by_id(dashboard_id="123")

        # Clear specific query
        clear_cache_by_id(query_id="456")

        # Clear both
        clear_cache_by_id(dashboard_id="123", query_id="456")

    Note: This clears ALL cached field variants for the resource.
    For example, dashboard "123" might be cached with fields "id,title"
    AND "id,title,dashboard_elements" - both will be cleared.
    """
    _ensure_env_vars()

    with LookerClient() as client:
        total_deleted = 0
        resources_cleared = []

        if dashboard_id:
            # Clear dashboard and dashboard_lookml
            deleted = client.invalidate_cache_by_id("dashboard", "dashboard_id", dashboard_id)
            total_deleted += deleted

            deleted = client.invalidate_cache_by_id(
                "dashboard_lookml", "dashboard_id", dashboard_id
            )
            total_deleted += deleted

            resources_cleared.append(f"dashboard:{dashboard_id}")

        if query_id:
            deleted = client.invalidate_cache_by_id("query", "query_id", query_id)
            total_deleted += deleted
            resources_cleared.append(f"query:{query_id}")

        return {
            "deleted": total_deleted,
            "resources_cleared": resources_cleared,
        }


@mcp.tool()
def cleanup_expired_cache() -> dict[str, Any]:
    """
    Remove expired cache entries.

    Returns:
        Dictionary with:
        - deleted: Number of expired entries removed

    Example:
        result = cleanup_expired_cache()
        print(f"Removed {result['deleted']} expired entries")

    Note: Cache entries expire based on TTL (default: 1 hour).
    This is useful for freeing disk space.
    """
    _ensure_env_vars()

    with LookerClient() as client:
        deleted = client.cleanup_cache()

        return {"deleted": deleted}


# ============================================================================
# Server Entry Point
# ============================================================================


def run_server(transport: str = "stdio") -> None:
    """
    Run the MCP server.

    Args:
        transport: Transport protocol to use ("stdio", "sse", or "streamable-http")
    """
    mcp.run(transport=transport)  # type: ignore
