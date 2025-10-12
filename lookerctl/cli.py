#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "looker-sdk>=24.0.0",
#   "click>=8.1.0",
#   "rich>=13.0.0",
#   "pydantic>=2.0.0",
#   "gitpython>=3.1.0",
#   "lkml>=1.3.0",
#   "networkx>=3.0.0",
#   "python-dotenv>=1.0.0",
#   "mcp>=1.0.0",
#   "PyYAML>=6.0.0",
# ]
# requires-python = ">=3.10"
# ///
# vi: set ft=python
"""
Looker SDK CLI - Comprehensive suite for managing and analyzing Looker instances.

This CLI provides tools for:
- Session and workspace management
- LookML export and synchronization
- Content validation
- Usage analysis and optimization
- Dependency mapping
"""

import json
import os
import sys
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

import click
from rich.console import Console

sys.path.insert(0, str(Path(__file__).parent))

from lookerctl.commands.analyze import (
    analyze_all_usage,
    analyze_specific_dashboards,
    export_usage_analysis,
    find_dashboards_using_explore,
    find_unused_explores,
    get_explore_fields,
    get_folder_dependencies,
    get_folder_inventory,
    get_folder_performance,
    list_all_explores,
    list_all_folders,
    print_explore_fields,
    print_explores_list,
    print_folder_dependencies,
    print_folder_inventory,
    print_folder_performance,
    print_folders_list,
    print_usage_summary,
    trace_field_usage,
)
from lookerctl.commands.deps import (
    analyze_impact,
    build_dependency_graph,
    export_dependency_graph,
    find_circular_dependencies,
    get_orphaned_views,
    get_statistics,
    print_dependency_tree,
    print_impact_analysis,
)
from lookerctl.commands.export import (
    export_all_content,
    export_all_dashboards,
    export_all_lookml,
    export_all_looks,
    export_project_files,
    push_local_files_to_looker,
    sync_project_from_git,
    validate_local_changes,
)
from lookerctl.commands.session import (
    checkout_git_branch,
    create_dev_branch,
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
    print_comparison_results,
    print_test_result,
    run_all_golden_tests,
    run_golden_test,
    run_query_and_capture,
)
from lookerctl.core.client import LookerClient
from lookerctl.core.config import verify_env_vars
from lookerctl.core.session_storage import get_preferred_workspace
from lookerctl.utils.lookml_project import LookMLProject

console = Console()


def requires_env_vars(f):
    """Decorator that ensures environment variables are verified before function execution."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        verify_env_vars()
        return f(*args, **kwargs)

    return wrapper


@click.group()
@click.version_option(version="0.1.0")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """
    Looker SDK CLI - Manage and analyze your Looker instance.

    Set these environment variables (source .env):
      LOOKERSDK_BASE_URL       - Your Looker instance URL
      LOOKERSDK_CLIENT_ID      - API client ID
      LOOKERSDK_CLIENT_SECRET  - API client secret
      LOOKERSDK_API_VERSION    - API version (default: 4.0)
      LOOKERSDK_VERIFY_SSL     - Verify SSL (default: true)
    """
    ctx.ensure_object(dict)


@cli.group()
def session() -> None:
    """Manage Looker workspaces and sessions."""
    pass


@cli.group()
def export() -> None:
    """Export and sync LookML content."""
    pass


@export.command("project")
@click.argument("project_id", required=False)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    default=Path("./looker_export"),
    help="Output directory for exported files",
)
@click.option("--branch", "-b", help="Git branch to export from")
@requires_env_vars
def export_project(project_id: str | None, output_dir: Path, branch: str | None) -> None:
    """
    Export LookML files from a single project.

    If PROJECT_ID is not provided, attempts to use first available project.
    """
    try:
        with LookerClient() as client:
            # If no project_id provided, get all projects and use first one
            if not project_id:
                projects = client.get_all_projects()
                if not projects:
                    console.print("[red]Error:[/red] No projects found")
                    sys.exit(1)
                project_id = projects[0].id
                assert project_id is not None
                console.print(f"Using project: {project_id}")

            stats = export_project_files(client, project_id, output_dir, branch)

            if stats["files_exported"] > 0:
                size_mb = stats["total_size"] / (1024 * 1024)
                console.print(
                    f"\n[green]✓[/green] Exported {stats['files_exported']} files "
                    f"({size_mb:.2f} MB) to {output_dir}"
                )
            else:
                console.print("[yellow]No files exported[/yellow]")

            if stats["errors"]:
                console.print(f"\n[yellow]Warnings:[/yellow] {len(stats['errors'])} error(s)")
                sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@export.command("all")
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    default=Path("./looker_export"),
    help="Base directory for exported files",
)
@requires_env_vars
def export_all(output_dir: Path) -> None:
    """Export LookML files from all projects."""
    try:
        with LookerClient() as client:
            stats = export_all_lookml(client, output_dir)

            console.print("\n[bold]Export Summary:[/bold]")
            console.print(f"  Projects: {stats['projects_exported']}")
            console.print(f"  Total files: {stats['total_files']}")
            size_mb = stats["total_size"] / (1024 * 1024)
            console.print(f"  Total size: {size_mb:.2f} MB")

            if stats["errors"]:
                console.print(f"\n[yellow]Warnings:[/yellow] {len(stats['errors'])} error(s)")
                for error in stats["errors"][:5]:
                    console.print(f"  • {error}")
                if len(stats["errors"]) > 5:
                    console.print(f"  ... and {len(stats['errors']) - 5} more")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@export.command("sync")
@click.argument("project_id", required=False)
@click.option("--branch", "-b", help="Git branch to sync to")
@requires_env_vars
def sync_project(project_id: str | None, branch: str | None) -> None:
    """
    Sync a project from its git repository.

    If PROJECT_ID is not provided, attempts to use first available project.
    """
    try:
        with LookerClient() as client:
            # If no project_id provided, get all projects and use first one
            if not project_id:
                projects = client.get_all_projects()
                if not projects:
                    console.print("[red]Error:[/red] No projects found")
                    sys.exit(1)
                project_id = projects[0].id
                assert project_id is not None
                console.print(f"Using project: {project_id}")

            result = sync_project_from_git(client, project_id, branch)

            if not result["success"]:
                console.print(f"[red]✗[/red] {result['message']}")
                sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@export.command("push")
@click.argument("project_id")
@click.argument("local_dir", type=click.Path(exists=True, path_type=Path))
@click.option("--no-validate", is_flag=True, help="Skip validation after push")
@requires_env_vars
def export_push(project_id: str, local_dir: Path, no_validate: bool) -> None:
    """
    Push local LookML files to Looker dev branch.

    This enables the local development workflow:
    1. Export LookML to local
    2. Make changes locally (AI or human)
    3. Push to Looker dev branch
    4. Get validation feedback
    5. Iterate

    This gives you a Looker console-like experience working locally.
    """
    try:
        with LookerClient() as client:
            result = push_local_files_to_looker(
                client, project_id, local_dir, validate_after=not no_validate
            )

            if result["files_pushed"] > 0:
                console.print(
                    f"\n[green]✓[/green] Pushed {result['files_pushed']} file(s) to project {project_id}"
                )

            if result["errors"]:
                console.print(f"\n[yellow]Encountered {len(result['errors'])} error(s)[/yellow]")
                sys.exit(1)

            if result.get("validation") and result["validation"]["has_errors"]:
                console.print("\n[red]Validation failed - see errors above[/red]")
                sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@export.command("dashboards")
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    default=Path("./looker_export/dashboards"),
    help="Output directory for dashboard LookML files",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    help="Limit number of dashboards to export (for testing)",
)
@requires_env_vars
def export_dashboards(output_dir: Path, limit: int | None) -> None:
    """
    Export all user-defined dashboards (UDDs) as LookML.

    User-defined dashboards are stored in Looker's database (not git)
    and can be exported using the dashboard_lookml() API.
    """
    try:
        with LookerClient() as client:
            stats = export_all_dashboards(client, output_dir, limit=limit)

            if stats["dashboards_exported"] > 0:
                size_mb = stats["total_size"] / (1024 * 1024)
                console.print(
                    f"\n[green]✓[/green] Exported {stats['dashboards_exported']} dashboards "
                    f"({size_mb:.2f} MB) to {output_dir}"
                )
            else:
                console.print("[yellow]No dashboards exported[/yellow]")

            if stats["errors"]:
                console.print(f"\n[yellow]Warnings:[/yellow] {len(stats['errors'])} error(s)")
                for error in stats["errors"][:5]:
                    console.print(f"  • {error}")
                if len(stats["errors"]) > 5:
                    console.print(f"  ... and {len(stats['errors']) - 5} more")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@export.command("looks")
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    default=Path("./looker_export/looks"),
    help="Output directory for look JSON files",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    help="Limit number of looks to export (for testing)",
)
@requires_env_vars
def export_looks(output_dir: Path, limit: int | None) -> None:
    """
    Export all looks (saved queries) as JSON.

    Looks are stored in Looker's database and include complete query definitions.
    """
    try:
        with LookerClient() as client:
            stats = export_all_looks(client, output_dir, limit=limit)

            if stats["looks_exported"] > 0:
                size_mb = stats["total_size"] / (1024 * 1024)
                console.print(
                    f"\n[green]✓[/green] Exported {stats['looks_exported']} looks "
                    f"({size_mb:.2f} MB) to {output_dir}"
                )
            else:
                console.print("[yellow]No looks exported[/yellow]")

            if stats["errors"]:
                console.print(f"\n[yellow]Warnings:[/yellow] {len(stats['errors'])} error(s)")
                for error in stats["errors"][:5]:
                    console.print(f"  • {error}")
                if len(stats["errors"]) > 5:
                    console.print(f"  ... and {len(stats['errors']) - 5} more")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@export.command("content")
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    default=Path("./looker_export"),
    help="Base directory for all exported content",
)
@requires_env_vars
def export_all_content_cmd(output_dir: Path) -> None:
    """
    Export all Looker content: dashboards and looks.

    Note: LookML project files (models, views, explores) should be
    managed via git clone/pull.
    """
    try:
        with LookerClient() as client:
            stats = export_all_content(client, output_dir)

            console.print("\n[bold]Export Summary:[/bold]")
            console.print(f"  Dashboards: {stats['dashboards_exported']}")
            console.print(f"  Looks: {stats['looks_exported']}")

            if stats["errors"]:
                console.print(f"\n[yellow]Warnings:[/yellow] {len(stats['errors'])} error(s)")
                for error in stats["errors"][:5]:
                    console.print(f"  • {error}")
                if len(stats["errors"]) > 5:
                    console.print(f"  ... and {len(stats['errors']) - 5} more")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@cli.group()
def validate() -> None:
    """Validate LookML content."""
    pass


@cli.group()
def analyze() -> None:
    """Analyze usage and exposure of explores/views."""
    pass


@analyze.command("usage")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for analysis results (JSON)",
)
@requires_env_vars
def analyze_usage_cmd(
    output: Path | None,
) -> None:
    """Analyze explore and field usage across dashboards and looks in known accounts."""
    try:
        with LookerClient() as client:
            analysis = analyze_all_usage(client)
            print_usage_summary(analysis)

            if output:
                export_usage_analysis(analysis, output)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@analyze.command("unused")
@requires_env_vars
def analyze_unused_cmd() -> None:
    """Find explores that are not used in any dashboards or looks."""
    try:
        with LookerClient() as client:
            console.print("\n[bold]Finding unused explores...[/bold]\n")

            analysis = analyze_all_usage(client)
            unused = find_unused_explores(client, analysis)

            if unused:
                console.print(f"[yellow]Found {len(unused)} unused explore(s):[/yellow]\n")
                for explore in unused[:20]:
                    console.print(f"  • {explore}")
                if len(unused) > 20:
                    console.print(f"\n  ... and {len(unused) - 20} more")
            else:
                console.print("[green]✓ All explores are being used![/green]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@analyze.command("explore")
@click.argument("explore_name")
@click.option("--model", "-m", help="Model name (if not specified in explore_name)")
@requires_env_vars
def analyze_explore_cmd(explore_name: str, model: str | None) -> None:
    """
    Analyze usage of a specific explore in known accounts.

    EXPLORE_NAME can be either 'explore_name' or 'model.explore_name'
    """
    try:
        # Parse explore name
        if "." in explore_name:
            model_name, explore = explore_name.split(".", 1)
        elif model:
            model_name = model
            explore = explore_name
        else:
            console.print(
                "[red]Error:[/red] Please specify model either in explore_name "
                "(model.explore) or with --model flag"
            )
            sys.exit(1)

        explore_key = f"{model_name}.{explore}"

        with LookerClient() as client:
            console.print(f"\n[bold]Analyzing explore: {explore_key}[/bold]\n")

            analysis = analyze_all_usage(client)

            if explore_key not in analysis["usage_map"]:
                console.print(f"[yellow]No usage found for {explore_key}[/yellow]")
                console.print("\nThis explore is either:")
                console.print("  • Not used in any dashboards or looks")
                console.print("  • Does not exist in the instance")
                return

            fields = analysis["usage_map"][explore_key]
            console.print(f"Found {len(fields)} field(s) in use:\n")

            for field, locations in sorted(fields.items()):
                console.print(f"[cyan]{field}[/cyan]")
                console.print(f"  Used in {len(locations)} location(s):")
                for location in sorted(locations)[:5]:
                    console.print(f"    • {location}")
                if len(locations) > 5:
                    console.print(f"    ... and {len(locations) - 5} more")
                console.print()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@analyze.command("explore-fields")
@click.argument("explore_name")
@click.option("--model", "-m", help="Model name (if not specified in explore_name)")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for field data (JSON)",
)
@click.option("--show-hidden", is_flag=True, help="Show hidden fields")
@requires_env_vars
def analyze_explore_fields_cmd(
    explore_name: str, model: str | None, output: Path | None, show_hidden: bool
) -> None:
    """
    Discover all available fields in an explore.

    This queries the Looker API for the actual runtime schema,
    showing what fields are really available (including from joined views).

    EXPLORE_NAME can be either 'explore_name' or 'model.explore_name'

    Perfect for:
    - Generating query files for baselines
    - Understanding explore structure
    - AI discovering available fields
    """
    try:
        # Parse explore name
        if "." in explore_name:
            model_name, explore = explore_name.split(".", 1)
        elif model:
            model_name = model
            explore = explore_name
        else:
            console.print(
                "[red]Error:[/red] Please specify model either in explore_name "
                "(model.explore) or with --model flag"
            )
            sys.exit(1)

        with LookerClient() as client:
            console.print(f"\n[bold]Discovering fields for {model_name}.{explore}...[/bold]\n")

            explore_data = get_explore_fields(client, model_name, explore)

            # Print to console
            print_explore_fields(explore_data, show_hidden=show_hidden)

            # Export to JSON if requested
            if output:
                output.write_text(json.dumps(explore_data, indent=2))
                console.print(f"[green]✓[/green] Exported field data to {output}\n")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@analyze.command("list-explores")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for explore list (JSON)",
)
@click.option("--show-hidden", is_flag=True, help="Show hidden explores")
@requires_env_vars
def analyze_list_explores_cmd(output: Path | None, show_hidden: bool) -> None:
    """
    List all available model.explore combinations in the Looker instance.

    This helps you discover the correct model.explore format to use in
    baseline creation, AB tests, and golden tests.

    Example:
        ./looker.py analyze list-explores
        ./looker.py analyze list-explores -o explores.json
        ./looker.py analyze list-explores --show-hidden
    """
    try:
        with LookerClient() as client:
            console.print("\n[bold]Discovering all explores...[/bold]\n")

            explores = list_all_explores(client)

            # Print to console
            print_explores_list(explores, show_hidden=show_hidden)

            # Export to JSON if requested
            if output:
                export_data = {
                    "total_explores": len(explores),
                    "explores": explores,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
                output.write_text(json.dumps(export_data, indent=2))
                console.print(f"[green]✓[/green] Exported explore list to {output}\n")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@analyze.command("list-folders")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for folder list (JSON)",
)
@requires_env_vars
def analyze_list_folders_cmd(output: Path | None) -> None:
    """
    List all folders in the Looker instance.

    Displays folders in a hierarchical tree structure showing folder IDs and names.

    Example:
        ./looker.py analyze list-folders
        ./looker.py analyze list-folders -o folders.json
    """
    try:
        with LookerClient() as client:
            console.print("\n[bold]Listing all folders...[/bold]\n")

            folders = list_all_folders(client)

            # Print to console
            print_folders_list(folders)

            # Export to JSON if requested
            if output:
                export_data = {
                    "total_folders": len(folders),
                    "folders": folders,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
                output.write_text(json.dumps(export_data, indent=2))
                console.print(f"[green]✓[/green] Exported folder list to {output}\n")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@analyze.command("dashboard")
@click.argument("dashboard_ids")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for analysis results (JSON)",
)
@requires_env_vars
def analyze_dashboard_cmd(dashboard_ids: str, output: Path | None) -> None:
    """
    Analyze explore and field usage for specific dashboard(s).

    Fast alternative to 'analyze usage' - only fetches the dashboards you specify.
    DASHBOARD_IDS can be a single ID or comma-separated list (e.g., "123" or "123,456,789")

    Example:
        ./looker.py analyze dashboard 123
        ./looker.py analyze dashboard 123,456,789 -o analysis.json
    """
    try:
        # Parse dashboard IDs
        ids = [id.strip() for id in dashboard_ids.split(",")]

        with LookerClient() as client:
            console.print(f"\n[bold]Analyzing {len(ids)} dashboard(s)...[/bold]\n")

            analysis = analyze_specific_dashboards(client, ids)

            # Print summary
            console.print("\n[bold]Analysis Summary[/bold]\n")
            console.print(f"Dashboards requested: {analysis['stats']['dashboards_requested']}")
            console.print(f"Dashboards analyzed: {analysis['stats']['dashboards_analyzed']}")
            console.print(f"Dashboards failed: {analysis['stats']['dashboards_failed']}")
            console.print(f"Explores found: {len(analysis['stats']['explores_found'])}")

            # Print usage details
            if analysis["usage_map"]:
                console.print("\n[bold]Explore & Field Usage:[/bold]\n")
                for explore_key, fields in sorted(analysis["usage_map"].items()):
                    console.print(f"[cyan]{explore_key}[/cyan]")
                    for field, locations in sorted(fields.items()):
                        console.print(f"  • {field}")
                        console.print(f"    Used in {len(locations)} location(s)")
                    console.print()

            # Export to JSON if requested
            if output:
                export_usage_analysis(analysis, output)

            if analysis["stats"]["errors"]:
                console.print(
                    f"\n[yellow]Encountered {len(analysis['stats']['errors'])} error(s)[/yellow]"
                )
                for error in analysis["stats"]["errors"][:5]:
                    console.print(f"  • {error}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@analyze.command("dashboards-using")
@click.argument("explore_key")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for dashboard list (JSON)",
)
@click.option("--limit", "-l", type=int, help="Limit number of results shown")
@requires_env_vars
def analyze_dashboards_using_cmd(explore_key: str, output: Path | None, limit: int | None) -> None:
    """
    Find all dashboards that use a specific explore (fast, metadata only).

    EXPLORE_KEY must be in 'model.explore' format (e.g., 'hub.CE_aws')

    This only fetches dashboard IDs and titles, making it very fast even with 15K+
    dashboards. Use this to identify candidates before doing deep analysis.

    Example:
        ./looker.py analyze dashboards-using hub.CE_aws
        ./looker.py analyze dashboards-using hub.CE_aws --limit 20 -o dashboards.json
    """
    try:
        with LookerClient() as client:
            console.print(f"\n[bold]Finding dashboards using: {explore_key}[/bold]\n")

            result = find_dashboards_using_explore(client, explore_key)

            # Print summary
            console.print("\n[bold]Search Summary[/bold]\n")
            console.print(f"Total dashboards checked: {result['total_dashboards_checked']}")
            console.print(f"Dashboards using {explore_key}: {result['total_matches']}")

            # Print matching dashboards
            if result["dashboards"]:
                console.print("\n[bold]Matching Dashboards:[/bold]\n")

                dashboards_to_show = result["dashboards"]
                if limit and limit > 0:
                    dashboards_to_show = dashboards_to_show[:limit]

                for dashboard in dashboards_to_show:
                    console.print(f"  • [cyan]{dashboard['id']}[/cyan]: {dashboard['title']}")

                if limit and len(result["dashboards"]) > limit:
                    console.print(
                        f"\n  ... and {len(result['dashboards']) - limit} more (use --limit to see more)"
                    )
            else:
                console.print(f"\n[yellow]No dashboards found using {explore_key}[/yellow]")

            # Export to JSON if requested
            if output:
                export_data = {
                    "explore_key": explore_key,
                    "total_dashboards_checked": result["total_dashboards_checked"],
                    "total_matches": result["total_matches"],
                    "dashboards": result["dashboards"],
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
                output.write_text(json.dumps(export_data, indent=2))
                console.print(f"\n[green]✓[/green] Exported dashboard list to {output}")

            if result["errors"]:
                console.print(f"\n[yellow]Encountered {len(result['errors'])} error(s)[/yellow]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@analyze.command("folder-inventory")
@click.argument("folder_name")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for inventory (JSON)",
)
@requires_env_vars
def analyze_folder_inventory_cmd(folder_name: str, output: Path | None) -> None:
    """
    Get inventory of content for folders matching a specific name.

    FOLDER_NAME is a folder name or identifier to search for.

    Shows:
    - Folders matching the name
    - Dashboards and looks in those folders
    - Total content counts

    Example:
        ./looker.py analyze folder-inventory my-folder
        ./looker.py analyze folder-inventory projects -o inventory.json
    """
    try:
        with LookerClient() as client:
            console.print(f"\n[bold]Getting inventory for folder: {folder_name}[/bold]\n")

            inventory = get_folder_inventory(client, folder_name)
            print_folder_inventory(inventory)

            if output:
                export_data = {
                    **inventory,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
                output.write_text(json.dumps(export_data, indent=2))
                console.print(f"\n[green]✓[/green] Exported inventory to {output}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@analyze.command("folder-dependencies")
@click.argument("folder_name")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for dependency analysis (JSON)",
)
@requires_env_vars
def analyze_folder_dependencies_cmd(folder_name: str, output: Path | None) -> None:
    """
    Analyze dependencies for folders matching a specific name.

    FOLDER_NAME is a folder name or identifier to search for.

    Shows:
    - Which explores the folder's dashboards use
    - Which fields from each explore they depend on
    - Total field usage counts per explore

    This helps understand the impact of schema changes on specific folders.

    Example:
        ./looker.py analyze folder-dependencies my-folder
        ./looker.py analyze folder-dependencies projects -o deps.json
    """
    try:
        with LookerClient() as client:
            console.print(f"\n[bold]Analyzing dependencies for folder: {folder_name}[/bold]\n")

            dependencies = get_folder_dependencies(client, folder_name)
            print_folder_dependencies(dependencies)

            if output:
                export_data = {
                    **dependencies,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
                output.write_text(json.dumps(export_data, indent=2))
                console.print(f"\n[green]✓[/green] Exported dependencies to {output}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@analyze.command("folder-performance")
@click.argument("folder_name")
@click.option(
    "--threshold",
    "-t",
    type=float,
    default=5.0,
    help="Slow query threshold in seconds (default: 5.0)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for performance analysis (JSON)",
)
@requires_env_vars
def analyze_folder_performance_cmd(folder_name: str, threshold: float, output: Path | None) -> None:
    """
    Identify dashboards with performance issues for folders matching a specific name.

    FOLDER_NAME is a folder name or identifier to search for.

    Shows:
    - Dashboards with slow queries (above threshold)
    - Query runtime metrics
    - Average runtime per dashboard
    - Number of slow queries per dashboard

    This helps identify performance bottlenecks in folder content.

    Example:
        ./looker.py analyze folder-performance my-folder
        ./looker.py analyze folder-performance projects --threshold 10.0
        ./looker.py analyze folder-performance my-folder -o perf.json
    """
    try:
        with LookerClient() as client:
            console.print(f"\n[bold]Analyzing performance for folder: {folder_name}[/bold]\n")

            performance = get_folder_performance(client, folder_name, threshold)
            print_folder_performance(performance)

            if output:
                export_data = {
                    **performance,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
                output.write_text(json.dumps(export_data, indent=2))
                console.print(f"\n[green]✓[/green] Exported performance analysis to {output}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@analyze.command("field")
@click.argument("field_name")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for usage results (JSON)",
)
@requires_env_vars
def analyze_field_cmd(field_name: str, output: Path | None) -> None:
    """
    Trace usage of a specific field across all dashboards and looks.

    Surgical alternative to 'analyze usage' - only tracks one field instead of
    analyzing everything. Much faster when you need to understand where a specific
    field is used.

    FIELD_NAME should be in 'view.field' format (e.g., 'aws_cost.total_cost', 'users.count')

    Example:
        ./looker.py analyze field aws_cost.total_cost
        ./looker.py analyze field users.count -o field_usage.json
    """
    try:
        with LookerClient() as client:
            console.print(f"\n[bold]Tracing field usage: {field_name}[/bold]\n")

            result = trace_field_usage(client, field_name)

            # Print summary
            console.print("\n[bold]Usage Summary[/bold]\n")
            console.print(f"Field: {field_name}")
            console.print(f"Total usage: {result['total_usage']} location(s)")
            console.print(f"  - Dashboards: {result['total_dashboard_usage']}")
            console.print(f"  - Looks: {result['total_look_usage']}")
            console.print(f"Queries analyzed: {result['stats']['queries_analyzed']}")

            # Print dashboards using this field
            if result["dashboards"]:
                console.print(f"\n[bold]Dashboards using '{field_name}':[/bold]\n")
                for dashboard in result["dashboards"]:
                    console.print(f"  • [cyan]{dashboard['id']}[/cyan]: {dashboard['title']}")
                    console.print(f"    Explores: {', '.join(dashboard['explores'])}")
                    console.print(f"    Queries using field: {dashboard['query_count']}")
                    console.print()

            # Print looks using this field
            if result["looks"]:
                console.print(f"\n[bold]Looks using '{field_name}':[/bold]\n")
                for look in result["looks"]:
                    console.print(f"  • [cyan]{look['id']}[/cyan]: {look['title']}")
                    console.print(f"    Explore: {look['explore']}")
                    console.print()

            if not result["dashboards"] and not result["looks"]:
                console.print(f"\n[yellow]No usage found for field '{field_name}'[/yellow]")
                console.print("\nThis field is either:")
                console.print("  • Not used in any dashboards or looks")
                console.print("  • Misspelled (check field name)")
                console.print("  • Only used in private/inaccessible content")

            # Export to JSON if requested
            if output:
                export_data = {
                    **result,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
                # Convert stats for JSON serialization
                export_data["stats"] = dict(result["stats"])

                output.write_text(json.dumps(export_data, indent=2))
                console.print(f"\n[green]✓[/green] Exported field usage to {output}")

            if result["stats"]["errors"]:
                console.print(
                    f"\n[yellow]Encountered {len(result['stats']['errors'])} error(s)[/yellow]"
                )

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@analyze.command("explore-fields-local")
@click.argument("project_dir", type=click.Path(exists=True, path_type=Path))
@click.argument("explore_name")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for field data (JSON)",
)
@click.option("--show-hidden", is_flag=True, help="Show hidden fields")
def analyze_explore_fields_local_cmd(
    project_dir: Path, explore_name: str, output: Path | None, show_hidden: bool
) -> None:
    """
    Discover explore fields locally without API calls (instant).

    This parses local LookML files to determine available fields,
    resolving:
    - Base view fields (with extends inheritance)
    - Joined view fields
    - Field scoping rules
    - Hidden fields

    This is MUCH faster than 'explore-fields' because it doesn't
    require API calls. Perfect for rapid iteration and offline work.

    Example:
        ./looker.py analyze explore-fields-local ./lookml my_explore
        ./looker.py analyze explore-fields-local ./lookml my_explore -o fields.json
    """
    try:
        console.print(f"\n[bold]Parsing LookML project:[/bold] {project_dir}\n")

        # Load project
        project = LookMLProject(project_dir, console=console)

        console.print(
            f"[green]✓[/green] Loaded {len(project.views)} views, "
            f"{len(project.explores)} explores\n"
        )

        # Get explore fields
        console.print(f"[bold]Discovering fields for explore:[/bold] {explore_name}\n")

        fields = project.get_explore_fields(explore_name, include_hidden=show_hidden)

        # Print summary
        dim_count = len(fields["dimensions"])
        meas_count = len(fields["measures"])
        filter_count = len(fields["filters"])
        param_count = len(fields["parameters"])

        console.print("[bold]Field Summary:[/bold]")
        console.print(f"  Dimensions: {dim_count}")
        console.print(f"  Measures: {meas_count}")
        console.print(f"  Filters: {filter_count}")
        console.print(f"  Parameters: {param_count}")
        console.print(
            f"  [bold]Total: {dim_count + meas_count + filter_count + param_count}[/bold]\n"
        )

        # Print field details
        if fields["dimensions"]:
            console.print("[bold cyan]Dimensions:[/bold cyan]")
            for field in fields["dimensions"][:20]:
                field_info = f"  • {field.name}"
                if field.type:
                    field_info += f" ({field.type})"
                if field.description:
                    field_info += f" - {field.description[:60]}"
                console.print(field_info)
            if len(fields["dimensions"]) > 20:
                console.print(f"  ... and {len(fields['dimensions']) - 20} more")
            console.print()

        if fields["measures"]:
            console.print("[bold green]Measures:[/bold green]")
            for field in fields["measures"][:20]:
                field_info = f"  • {field.name}"
                if field.type:
                    field_info += f" ({field.type})"
                if field.description:
                    field_info += f" - {field.description[:60]}"
                console.print(field_info)
            if len(fields["measures"]) > 20:
                console.print(f"  ... and {len(fields['measures']) - 20} more")
            console.print()

        # Export to JSON if requested
        if output:
            export_data = {
                "explore": explore_name,
                "fields": {
                    "dimensions": [
                        {
                            "name": f.name,
                            "type": f.type,
                            "description": f.description,
                            "sql": f.sql,
                            "hidden": f.hidden,
                        }
                        for f in fields["dimensions"]
                    ],
                    "measures": [
                        {
                            "name": f.name,
                            "type": f.type,
                            "description": f.description,
                            "sql": f.sql,
                            "hidden": f.hidden,
                        }
                        for f in fields["measures"]
                    ],
                    "filters": [{"name": f.name, "type": f.type} for f in fields["filters"]],
                    "parameters": [{"name": f.name, "type": f.type} for f in fields["parameters"]],
                },
            }
            output.write_text(json.dumps(export_data, indent=2))
            console.print(f"[green]✓[/green] Exported field data to {output}\n")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@cli.group("query-test")
def query_test() -> None:
    """Query testing, baselines, and golden tests."""
    pass


@query_test.group("baseline")
def test_baseline() -> None:
    """Create and compare query baselines for AB testing."""
    pass


@query_test.group("golden")
def test_golden() -> None:
    """Manage golden tests with expected results."""
    pass


@test_baseline.command("create")
@click.argument("explore")
@click.option(
    "--query-file",
    "-q",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="JSON file with query specification",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for baseline (not used in dry-run mode)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate query without creating baseline (test run only)",
)
@requires_env_vars
def baseline_create(explore: str, query_file: Path, output: Path | None, dry_run: bool) -> None:
    """
    Create a baseline by running a query and capturing results.

    EXPLORE should be in format 'model.explore_name'

    Query file should be JSON with: fields, filters, sorts, limit

    Example query file:
    {
      "fields": ["users.count", "users.city"],
      "filters": {"users.state": "California"},
      "sorts": ["users.count desc"],
      "limit": "100"
    }
    """
    try:
        # Parse explore
        if "." not in explore:
            console.print("[red]Error:[/red] Explore must be in format 'model.explore_name'")
            sys.exit(1)

        model, explore_name = explore.split(".", 1)

        # Load query spec
        query_spec = json.loads(query_file.read_text())

        # Validate arguments
        if not dry_run and not output:
            console.print("[red]Error:[/red] --output is required unless using --dry-run")
            sys.exit(1)

        with LookerClient() as client:
            if dry_run:
                # Dry run mode - just validate the query
                console.print(
                    f"\n[bold]DRY RUN - Validating query for {model}.{explore_name}[/bold]\n"
                )

                result = run_query_and_capture(client, model, explore_name, query_spec)

                console.print("[green]✓[/green] Query validation successful!")
                console.print(f"  Rows returned: {result['row_count']}")
                console.print(f"  Runtime: {result['performance']['runtime_seconds']:.2f}s")
                console.print(f"  Status: {result['performance']['status']}")
                console.print("\n[yellow]Note:[/yellow] Baseline not created (dry-run mode)")
                console.print("      Remove --dry-run to create baseline\n")

            else:
                # Normal mode - create baseline
                assert output is not None  # Guaranteed by check at line 834
                create_baseline(client, model, explore_name, query_spec, output)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@test_baseline.command("compare")
@click.argument("explore")
@click.option(
    "--baseline",
    "-b",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Baseline file to compare against",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for comparison results (JSON)",
)
@click.option(
    "--tolerance",
    type=float,
    default=0.01,
    help="Numeric tolerance for comparisons",
)
@requires_env_vars
def baseline_compare(explore: str, baseline: Path, output: Path | None, tolerance: float) -> None:
    """
    Run query and compare results to baseline.

    EXPLORE should be in format 'model.explore_name'

    This will:
    1. Load baseline query and results
    2. Run same query against current explore
    3. Compare results and performance
    4. Show differences
    """
    try:
        # Parse explore
        if "." not in explore:
            console.print("[red]Error:[/red] Explore must be in format 'model.explore_name'")
            sys.exit(1)

        model, explore_name = explore.split(".", 1)

        with LookerClient() as client:
            comparison = compare_to_baseline(
                client,
                model,
                explore_name,
                baseline,
                tolerance={"numeric_tolerance": tolerance},
            )

            print_comparison_results(comparison)

            if output:
                output.write_text(json.dumps(comparison, indent=2))
                console.print(f"[green]✓[/green] Comparison saved to {output}")

            if not comparison["passed"]:
                sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@query_test.command("sql")
@click.argument("explore")
@click.option(
    "--query-file",
    "-q",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="JSON file with query specification",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for SQL (otherwise prints to console)",
)
@requires_env_vars
def query_sql(explore: str, query_file: Path, output: Path | None) -> None:
    """
    Get the SQL that Looker would generate without executing the query.

    EXPLORE should be in format 'model.explore_name'

    Query file should be JSON with: fields, filters, sorts, limit

    Example query file:
    {
      "fields": ["users.count", "users.city"],
      "filters": {"users.state": "California"},
      "sorts": ["users.count desc"],
      "limit": "100"
    }

    This is useful for:
    - Understanding what SQL Looker generates
    - Debugging query issues
    - Query profiling and optimization
    - Running dry-run validations in BigQuery
    """
    try:
        # Parse explore
        if "." not in explore:
            console.print("[red]Error:[/red] Explore must be in format 'model.explore_name'")
            sys.exit(1)

        model, explore_name = explore.split(".", 1)

        # Load query spec
        query_spec = json.loads(query_file.read_text())

        # Extract parameters
        fields = query_spec.get("fields", [])
        filters = query_spec.get("filters")
        sorts = query_spec.get("sorts")
        limit = int(query_spec.get("limit", 500))

        with LookerClient() as client:
            result = get_rendered_sql(
                client,
                model,
                explore_name,
                fields,
                filters=filters,
                sorts=sorts,
                limit=limit,
            )

            sql = result["sql"]

            if output:
                output.write_text(sql)
                console.print(f"[green]✓[/green] SQL written to {output}")
            else:
                console.print("\n[bold]Generated SQL:[/bold]\n")
                console.print(sql)
                console.print()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@test_golden.command("create")
@click.argument("explore")
@click.option("--name", "-n", required=True, help="Test name")
@click.option(
    "--query-file",
    "-q",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="JSON file with query specification",
)
@click.option(
    "--expected-file",
    "-e",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="JSON file with expected results",
)
@click.option(
    "--test-dir",
    "-d",
    type=click.Path(path_type=Path),
    default=Path("./golden_tests"),
    help="Directory to store tests",
)
@click.option(
    "--scope",
    type=click.Choice(["permanent", "feature_branch"]),
    default="permanent",
    help="Test scope",
)
def golden_create(
    explore: str,
    name: str,
    query_file: Path,
    expected_file: Path,
    test_dir: Path,
    scope: str,
) -> None:
    """
    Create a golden test with expected results.

    EXPLORE should be in format 'model.explore_name'

    Expected file should be JSON with:
    {
      "row_count": 10,
      "schema": {"field1": "string", "field2": "number"},
      "data": [...]  // optional - actual data to validate
    }
    """
    try:
        # Parse explore
        if "." not in explore:
            console.print("[red]Error:[/red] Explore must be in format 'model.explore_name'")
            sys.exit(1)

        model, explore_name = explore.split(".", 1)

        # Load specs
        query_spec = json.loads(query_file.read_text())
        expected = json.loads(expected_file.read_text())

        create_golden_test(name, model, explore_name, query_spec, expected, test_dir, scope)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@test_golden.command("run")
@click.option("--name", "-n", help="Run specific test by name")
@click.option(
    "--test-dir",
    "-d",
    type=click.Path(exists=True, path_type=Path),
    default=Path("./golden_tests"),
    help="Directory containing tests",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for results (JSON)",
)
@requires_env_vars
def golden_run(name: str | None, test_dir: Path, output: Path | None) -> None:
    """
    Run golden tests.

    If --name is specified, runs only that test.
    Otherwise, runs all tests in the directory.
    """
    try:
        with LookerClient() as client:
            if name:
                # Run specific test
                test_file = test_dir / f"{name}.json"
                if not test_file.exists():
                    console.print(f"[red]Error:[/red] Test not found: {name}")
                    sys.exit(1)

                result = run_golden_test(client, test_file)
                print_test_result(result)

                if output:
                    output.write_text(json.dumps(result, indent=2))

                if not result["passed"]:
                    sys.exit(1)

            else:
                # Run all tests
                summary = run_all_golden_tests(client, test_dir)

                if output:
                    output.write_text(json.dumps(summary, indent=2))

                if summary["failed"] > 0:
                    sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@test_golden.command("list")
@click.option(
    "--test-dir",
    "-d",
    type=click.Path(exists=True, path_type=Path),
    default=Path("./golden_tests"),
    help="Directory containing tests",
)
def golden_list(test_dir: Path) -> None:
    """List all golden tests."""
    try:
        test_files = list(test_dir.glob("*.json"))

        if not test_files:
            console.print(f"[yellow]No tests found in {test_dir}[/yellow]")
            return

        console.print(f"\n[bold]Golden Tests ({len(test_files)})[/bold]\n")

        for test_file in sorted(test_files):
            test = json.loads(test_file.read_text())
            console.print(f"  • [cyan]{test['name']}[/cyan]")
            console.print(f"    Explore: {test['explore']}")
            console.print(f"    Scope: {test['metadata']['scope']}")
            console.print(f"    Created: {test['metadata']['created_at']}")
            console.print()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@test_golden.command("delete")
@click.option("--name", "-n", required=True, help="Test name to delete")
@click.option(
    "--test-dir",
    "-d",
    type=click.Path(exists=True, path_type=Path),
    default=Path("./golden_tests"),
    help="Directory containing tests",
)
def golden_delete(name: str, test_dir: Path) -> None:
    """Delete a golden test."""
    try:
        test_file = test_dir / f"{name}.json"

        if not test_file.exists():
            console.print(f"[red]Error:[/red] Test not found: {name}")
            sys.exit(1)

        test_file.unlink()
        console.print(f"[green]✓[/green] Deleted test: {name}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@cli.group()
def cache() -> None:
    """Manage API response cache."""
    pass


@cache.command("stats")
@requires_env_vars
def cache_stats() -> None:
    """Show cache statistics."""
    try:
        with LookerClient() as client:
            stats = client.get_cache_stats()

            if not stats:
                console.print("[yellow]Cache is disabled[/yellow]")
                return

            console.print("\n[bold]API Cache Statistics:[/bold]\n")
            console.print(f"  Total entries: {stats['total_entries']}")
            console.print(f"  Active entries: {stats['active_entries']}")
            console.print(f"  Expired entries: {stats['expired_entries']}")
            console.print(f"  Total cache hits: {stats['total_hits']}")
            console.print(f"  DB size: {stats['db_size_mb']:.2f} MB\n")

            if stats["endpoints"]:
                console.print("[bold]Entries by endpoint:[/bold]")
                for endpoint, count in sorted(stats["endpoints"].items()):
                    console.print(f"  {endpoint}: {count}")
                console.print()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@cache.command("clear")
@click.option("--endpoint", "-e", help="Clear specific endpoint only")
@click.option("--force", "-f", is_flag=True, help="Don't ask for confirmation")
@requires_env_vars
def cache_clear(endpoint: str | None, force: bool) -> None:
    """Clear cache entries."""
    try:
        with LookerClient() as client:
            if not client.use_cache:
                console.print("[yellow]Cache is disabled[/yellow]")
                return

            # Get stats before clearing
            stats = client.get_cache_stats()
            if not stats or stats["total_entries"] == 0:
                console.print("[yellow]Cache is empty[/yellow]")
                return

            # Confirm if not forced
            if not force:
                if endpoint:
                    msg = f"Clear {stats['endpoints'].get(endpoint, 0)} entries for endpoint '{endpoint}'?"
                else:
                    msg = f"Clear all {stats['total_entries']} cache entries?"

                if not click.confirm(msg):
                    console.print("Cancelled")
                    return

            # Clear cache
            deleted = client.invalidate_cache(endpoint=endpoint)

            if deleted > 0:
                console.print(f"[green]✓[/green] Cleared {deleted} cache entries")
            else:
                console.print("[yellow]No matching entries found[/yellow]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@cache.command("cleanup")
@requires_env_vars
def cache_cleanup() -> None:
    """Remove expired cache entries."""
    try:
        with LookerClient() as client:
            if not client.use_cache:
                console.print("[yellow]Cache is disabled[/yellow]")
                return

            deleted = client.cleanup_cache()

            if deleted > 0:
                console.print(f"[green]✓[/green] Removed {deleted} expired entries")
            else:
                console.print("[dim]No expired entries found[/dim]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@cache.command("clear-id")
@click.option("--dashboard", "-d", help="Clear specific dashboard by ID")
@click.option("--query", "-q", help="Clear specific query by ID")
@click.option("--look", "-l", help="Clear specific look by ID")
@requires_env_vars
def cache_clear_id(dashboard: str | None, query: str | None, look: str | None) -> None:
    """Clear cache for specific resource IDs.

    Examples:
        # Clear specific dashboard
        ./looker.py cache clear-id --dashboard 123

        # Clear specific query
        ./looker.py cache clear-id --query 456

        # Clear multiple resources
        ./looker.py cache clear-id --dashboard 123 --query 456
    """
    try:
        with LookerClient() as client:
            if not client.use_cache:
                console.print("[yellow]Cache is disabled[/yellow]")
                return

            total_deleted = 0

            if dashboard:
                # Clear dashboard and dashboard_lookml caches
                deleted = client.invalidate_cache_by_id("dashboard", "dashboard_id", dashboard)
                total_deleted += deleted
                console.print(
                    f"  [dim]Cleared {deleted} dashboard cache entries for ID {dashboard}[/dim]"
                )

                deleted = client.invalidate_cache_by_id(
                    "dashboard_lookml", "dashboard_id", dashboard
                )
                total_deleted += deleted
                console.print(
                    f"  [dim]Cleared {deleted} dashboard_lookml cache entries for ID {dashboard}[/dim]"
                )

            if query:
                deleted = client.invalidate_cache_by_id("query", "query_id", query)
                total_deleted += deleted
                console.print(f"  [dim]Cleared {deleted} query cache entries for ID {query}[/dim]")

            if look:
                # Looks don't have individual caches, only in the all_looks list
                console.print(
                    "  [yellow]Note: Looks are cached in bulk, use 'cache clear --endpoint all_looks'[/yellow]"
                )

            if total_deleted > 0:
                console.print(f"\n[green]✓[/green] Cleared {total_deleted} total cache entries")
            elif not any([dashboard, query, look]):
                console.print(
                    "[yellow]No resource ID specified. Use --dashboard, --query, or --look[/yellow]"
                )
            else:
                console.print("[dim]No matching cache entries found[/dim]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@cli.group()
def deps() -> None:
    """Analyze and visualize dependencies."""
    pass


@deps.command("build")
@click.argument("project_dir", type=click.Path(exists=True, path_type=Path), required=False)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for dependency graph (JSON or DOT format)",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["json", "dot"]),
    default="json",
    help="Output format",
)
@click.option(
    "--include-fields",
    is_flag=True,
    help="Include field-level nodes (warning: can make graph very large)",
)
@click.option(
    "--no-cache",
    is_flag=True,
    help="Disable cache and force full re-parse",
)
def deps_build(
    project_dir: Path | None, output: Path | None, format: str, include_fields: bool, no_cache: bool
) -> None:
    """
    Build dependency graph for a LookML project.

    PROJECT_DIR defaults to current directory if not specified.
    """
    try:
        if project_dir is None:
            project_dir = Path.cwd()

        graph = build_dependency_graph(
            project_dir, include_fields=include_fields, use_cache=not no_cache
        )
        stats = get_statistics(graph)

        console.print("[bold]Dependency Graph Statistics:[/bold]\n")
        console.print(f"  Total nodes: {stats['total_nodes']}")
        console.print(f"  Total edges: {stats['total_edges']}")
        console.print(f"  Views: {stats['total_views']}")
        console.print(f"  Explores: {stats['total_explores']}")
        console.print(f"  Dashboards: {stats['total_dashboards']}")
        console.print(f"  Avg dependencies per node: {stats['avg_dependencies']:.2f}")
        console.print(f"  Avg dependents per node: {stats['avg_dependents']:.2f}")

        if output:
            export_dependency_graph(graph, output, format)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@deps.command("tree")
@click.argument("node_name")
@click.argument("project_dir", type=click.Path(exists=True, path_type=Path), required=False)
@click.option("--depth", "-d", type=int, default=5, help="Maximum depth to traverse")
@click.option(
    "--include-fields",
    is_flag=True,
    help="Include field-level dependencies (shows which fields depend on which)",
)
def deps_tree(node_name: str, project_dir: Path | None, depth: int, include_fields: bool) -> None:
    """
    Show dependency tree for a view, explore, or field.

    NODE_NAME can be:
    - 'view_name' or 'view.view_name'
    - 'explore_name' or 'explore.explore_name'
    - 'view.view_name.field.field_name' (with --include-fields)

    PROJECT_DIR defaults to current directory if not specified.
    """
    try:
        if project_dir is None:
            project_dir = Path.cwd()

        graph = build_dependency_graph(project_dir, include_fields=include_fields)
        print_dependency_tree(graph, node_name, depth)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@deps.command("impact")
@click.argument("node_name")
@click.argument("project_dir", type=click.Path(exists=True, path_type=Path), required=False)
@click.option(
    "--include-fields",
    is_flag=True,
    help="Include field-level impact analysis (shows which fields would be affected)",
)
def deps_impact(node_name: str, project_dir: Path | None, include_fields: bool) -> None:
    """
    Analyze the impact of changing/removing a view, explore, or field.

    NODE_NAME can be:
    - 'view_name' or 'view.view_name'
    - 'explore_name' or 'explore.explore_name'
    - 'view.view_name.field.field_name' (with --include-fields)

    PROJECT_DIR defaults to current directory if not specified.
    """
    try:
        if project_dir is None:
            project_dir = Path.cwd()

        graph = build_dependency_graph(project_dir, include_fields=include_fields)
        analysis = analyze_impact(graph, node_name)
        print_impact_analysis(analysis)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@deps.command("orphaned")
@click.argument("project_dir", type=click.Path(exists=True, path_type=Path), required=False)
def deps_orphaned(project_dir: Path | None) -> None:
    """
    Find views that are not used by any explores.

    PROJECT_DIR defaults to current directory if not specified.
    """
    try:
        if project_dir is None:
            project_dir = Path.cwd()

        graph = build_dependency_graph(project_dir)
        orphaned = get_orphaned_views(graph)

        if orphaned:
            console.print(f"\n[yellow]Found {len(orphaned)} orphaned view(s):[/yellow]\n")
            for view in orphaned[:20]:
                console.print(f"  • {view}")
            if len(orphaned) > 20:
                console.print(f"\n  ... and {len(orphaned) - 20} more")
        else:
            console.print("\n[green]✓ No orphaned views found![/green]\n")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@deps.command("cycles")
@click.argument("project_dir", type=click.Path(exists=True, path_type=Path), required=False)
def deps_cycles(project_dir: Path | None) -> None:
    """
    Find circular dependencies in the LookML project.

    PROJECT_DIR defaults to current directory if not specified.
    """
    try:
        if project_dir is None:
            project_dir = Path.cwd()

        graph = build_dependency_graph(project_dir)
        cycles = find_circular_dependencies(graph)

        if cycles:
            console.print(f"\n[yellow]Found {len(cycles)} circular dependenc(ies):[/yellow]\n")
            for i, cycle in enumerate(cycles[:10], 1):
                console.print(f"  {i}. {' → '.join(cycle + [cycle[0]])}")
            if len(cycles) > 10:
                console.print(f"\n  ... and {len(cycles) - 10} more")
        else:
            console.print("\n[green]✓ No circular dependencies found![/green]\n")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@session.command("info")
@requires_env_vars
def session_info() -> None:
    """Show current session information and workspace preference."""
    try:
        with LookerClient() as client:
            sess = client.get_session()
            preferred = get_preferred_workspace()

            console.print("\n[bold]Current Session[/bold]")
            console.print(f"  Workspace ID: {sess.workspace_id}")
            console.print(f"  User ID: {sess.sudo_user_id or 'N/A'}")
            console.print("\n[bold]Saved Preference[/bold]")
            console.print(f"  Default workspace: {preferred}")
            console.print("  [dim](stored in .looker_session.json)[/dim]")
            console.print()
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@session.command("list-projects")
@requires_env_vars
def session_list_projects() -> None:
    """List all Looker projects."""
    try:
        with LookerClient() as client:
            projects = client.get_all_projects()

            if not projects:
                console.print("[yellow]No projects found[/yellow]")
                return

            console.print(f"\n[bold]Found {len(projects)} project(s):[/bold]\n")
            for project in projects:
                console.print(f"  • {project.name} [dim](ID: {project.id})[/dim]")
                if project.git_remote_url:
                    console.print(f"    Git: {project.git_remote_url}")
                if project.git_production_branch_name:
                    console.print(f"    Production branch: {project.git_production_branch_name}")
                console.print()
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@session.command("workspace")
@click.argument("workspace_id", type=click.Choice(["dev", "production"]))
@requires_env_vars
def session_workspace(workspace_id: str) -> None:
    """Switch to a different workspace (dev or production)."""
    try:
        with LookerClient() as client:
            result = switch_to_workspace(client, workspace_id)

            if not result["success"]:
                sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@session.command("checkout")
@click.argument("project_id")
@click.argument("branch")
@requires_env_vars
def session_checkout(project_id: str, branch: str) -> None:
    """Checkout a git branch in a Looker project."""
    try:
        with LookerClient() as client:
            result = checkout_git_branch(client, project_id, branch)

            if not result["success"]:
                sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@session.command("sync")
@click.argument("project_id", required=False)
@requires_env_vars
def session_sync(project_id: str | None) -> None:
    """
    Sync Looker project with local git branch.

    Detects the current git branch in your local repository and checks out
    the corresponding branch in Looker.

    If PROJECT_ID is not provided, attempts to use first available project.
    """
    try:
        with LookerClient() as client:
            # If no project_id provided, get all projects and use first one
            if not project_id:
                projects = client.get_all_projects()
                if not projects:
                    console.print("[red]Error:[/red] No projects found")
                    sys.exit(1)
                project_id = projects[0].id
                assert project_id is not None
                console.print(f"Using project: {project_id}\n")

            result = sync_with_local_git(client, project_id)

            if not result["success"]:
                sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@session.command("git-status")
@click.argument("project_id", required=False)
@requires_env_vars
def session_git_status(project_id: str | None) -> None:
    """
    Show git status for a Looker project.

    If PROJECT_ID is not provided, attempts to use first available project.
    """
    try:
        with LookerClient() as client:
            # If no project_id provided, get all projects and use first one
            if not project_id:
                projects = client.get_all_projects()
                if not projects:
                    console.print("[red]Error:[/red] No projects found")
                    sys.exit(1)
                project_id = projects[0].id
                assert project_id is not None

            status = get_project_git_status(client, project_id)

            if "error" in status:
                sys.exit(1)

            console.print(f"\n[bold]Git Status for {status['project_name']}[/bold]\n")
            console.print(f"  Project ID: {status['project_id']}")
            console.print(f"  Workspace: {status.get('workspace', 'unknown')}")
            console.print(f"  Remote URL: {status['git_remote_url']}")
            console.print(f"  Current branch: [cyan]{status['git_branch']}[/cyan]")
            console.print(f"  Production branch: {status['git_production_branch']}")

            # Show commit SHA if available
            if "commit_sha" in status:
                console.print(f"  Commit SHA: {status['commit_sha'][:8]}")

            # Show ahead/behind if available
            if "ahead_count" in status or "behind_count" in status:
                ahead = status.get("ahead_count", 0)
                behind = status.get("behind_count", 0)
                if ahead > 0 or behind > 0:
                    console.print(f"  Ahead/Behind: +{ahead}/-{behind}")

            if status["is_production_branch"]:
                console.print("\n  [yellow]⚠[/yellow] Currently on production branch")
            else:
                console.print("\n  [green]✓[/green] Currently on development branch")

            console.print()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@session.command("create-branch")
@click.argument("project_id")
@click.argument("branch_name")
@click.option("--from", "from_branch", help="Branch to create from (defaults to production)")
@requires_env_vars
def session_create_branch(project_id: str, branch_name: str, from_branch: str | None) -> None:
    """Create a new development branch in a Looker project."""
    try:
        with LookerClient() as client:
            result = create_dev_branch(client, project_id, branch_name, from_branch)

            if not result["success"]:
                sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@session.command("reset-to-remote")
@click.argument("project_id", required=False)
@requires_env_vars
def session_reset_to_remote(project_id: str | None) -> None:
    """
    Hard reset Looker project to match git remote.

    Discards any local changes in dev workspace and pulls the latest commit
    from git remote. Use this when Looker shows stale schema despite git being updated.

    If PROJECT_ID is not provided, attempts to use first available project.
    """
    try:
        with LookerClient() as client:
            # If no project_id provided, get all projects and use first one
            if not project_id:
                projects = client.get_all_projects()
                if not projects:
                    console.print("[red]Error:[/red] No projects found")
                    sys.exit(1)
                project_id = projects[0].id
                assert project_id is not None
                console.print(f"Using project: {project_id}\n")

            result = reset_to_remote(client, project_id)

            if not result["success"]:
                sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@validate.command("project")
@click.argument("project_id", required=False)
@requires_env_vars
def validate_project_cmd(project_id: str | None) -> None:
    """
    Validate LookML project in Looker.

    If PROJECT_ID is not provided, attempts to use first available project.
    """
    try:
        with LookerClient() as client:
            # If no project_id provided, get all projects and use first one
            if not project_id:
                projects = client.get_all_projects()
                if not projects:
                    console.print("[red]Error:[/red] No projects found")
                    sys.exit(1)
                project_id = projects[0].id
                assert project_id is not None
                console.print(f"Using project: {project_id}")

            console.print(f"\n[bold]Validating project:[/bold] {project_id}\n")

            result = client.validate_project(project_id)

            # Filter out errors that are outside the scope of the CLI
            # (infrastructure warnings that don't affect LookML correctness)
            ignored_error_patterns = [
                "legacy LookML runtime",  # Legacy runtime migration is infrastructure concern
            ]

            def should_ignore_error(error_msg: str) -> bool:
                """Check if error should be ignored (infrastructure warnings)."""
                return any(pattern in error_msg for pattern in ignored_error_patterns)

            # Separate real errors from ignored warnings
            real_errors = []
            ignored_warnings = []

            if result.errors:
                for error in result.errors:
                    if should_ignore_error(error.message):
                        ignored_warnings.append(error)
                    else:
                        real_errors.append(error)

            # Show ignored warnings (dimmed)
            if ignored_warnings:
                console.print("[dim]Ignoring infrastructure warnings (not LookML errors):[/dim]\n")
                for error in ignored_warnings:
                    console.print(f"  [dim]⚠ {error.message}[/dim]\n")

            # Show real errors
            if real_errors:
                console.print(f"[red]✗ Found {len(real_errors)} error(s):[/red]\n")
                for error in real_errors[:10]:  # Show first 10
                    console.print(f"  [red]ERROR:[/red] {error.message}")
                    if hasattr(error, "file_path") and error.file_path:
                        console.print(f"    File: {error.file_path}")
                    if hasattr(error, "line_number") and error.line_number:
                        console.print(f"    Line: {error.line_number}")
                    console.print()

                if len(real_errors) > 10:
                    console.print(f"  ... and {len(real_errors) - 10} more errors")

                sys.exit(1)
            else:
                console.print("[green]✓ Project validation passed![/green]\n")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@validate.command("local")
@click.argument("project_id")
@click.argument("local_dir", type=click.Path(exists=True, path_type=Path))
@requires_env_vars
def validate_local_cmd(project_id: str, local_dir: Path) -> None:
    """
    Validate local LookML files by pushing to Looker dev branch.

    This gives you the same validation experience as Looker console
    but working entirely with local files.

    Workflow:
    1. Pushes local files to Looker dev branch
    2. Validates in Looker
    3. Returns validation errors

    Perfect for AI-driven development - make changes locally,
    validate against Looker, get feedback, iterate.
    """
    try:
        with LookerClient() as client:
            result = validate_local_changes(client, project_id, local_dir)

            if result.get("validation") and result["validation"]["has_errors"]:
                console.print("\n[red]Validation failed - see errors above[/red]")
                sys.exit(1)
            elif result["files_pushed"] > 0:
                console.print(
                    f"\n[green]✓ Validated {result['files_pushed']} file(s) successfully[/green]"
                )

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@validate.command("static")
@click.argument("project_dir", type=click.Path(exists=True, path_type=Path), default=".")
@click.option("--view", "-v", help="Validate specific view only")
@click.option("--explore", "-e", help="Validate specific explore only")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output validation errors to JSON file",
)
def validate_static_cmd(
    project_dir: Path, view: str | None, explore: str | None, output: Path | None
) -> None:
    """
    Static LookML validation without API calls (66x faster).

    Validates LookML structure locally by:
    - Parsing all .lkml files in project directory
    - Building in-memory dependency graph
    - Validating field references
    - Checking for missing views/explores
    - Detecting circular dependencies

    This is MUCH faster than 'validate local' (600ms vs 40s) because
    it doesn't require pushing to Looker and waiting for API validation.

    Perfect for rapid iteration during development.

    Example:
        ./looker.py validate static ./lookml
        ./looker.py validate static ./lookml --view my_view
        ./looker.py validate static ./lookml --explore my_explore
    """
    try:
        console.print(f"\n[bold]Parsing LookML project:[/bold] {project_dir}\n")

        # Load project
        project = LookMLProject(project_dir, console=console)

        console.print(
            f"[green]✓[/green] Loaded {len(project.views)} views, "
            f"{len(project.explores)} explores, "
            f"{len(project.models)} models\n"
        )

        # Validate
        if view:
            console.print(f"[bold]Validating view:[/bold] {view}\n")
            errors = project.validate_view(view)
        elif explore:
            console.print(f"[bold]Validating explore:[/bold] {explore}\n")
            errors = project.validate_explore(explore)
        else:
            console.print("[bold]Validating all views and explores...[/bold]\n")
            errors = project.validate_all()

        # Print errors
        if errors:
            console.print(f"[red]Found {len(errors)} validation error(s):[/red]\n")
            for error in errors:
                console.print(f"  {error}")

            if output:
                output.write_text(
                    json.dumps(
                        [
                            {
                                "type": e.type,
                                "message": e.message,
                                "file": str(e.file_path),
                                "line": e.line_number,
                            }
                            for e in errors
                        ],
                        indent=2,
                    )
                )
                console.print(f"\n[green]✓[/green] Errors written to {output}")

            sys.exit(1)
        else:
            console.print("[green]✓ No validation errors found![/green]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@cli.command("test")
@requires_env_vars
def test() -> None:
    """Test Looker API connection and authentication."""
    try:
        console.print("\n[bold]Configuration:[/bold]")
        console.print(f"  Base URL: {os.getenv('LOOKERSDK_BASE_URL')}")
        console.print(f"  API Version: {os.getenv('LOOKERSDK_API_VERSION', '4.0')}")
        console.print(f"  Client ID: {os.getenv('LOOKERSDK_CLIENT_ID', '')[:8]}...")
        console.print(f"  Verify SSL: {os.getenv('LOOKERSDK_VERIFY_SSL', 'true')}\n")

        console.print("[bold]Testing connection...[/bold]\n")

        with LookerClient() as client:
            # Get session info
            sess = client.get_session()
            console.print(f"[green]✓[/green] Session workspace: {sess.workspace_id}")

            # Get projects
            projects = client.get_all_projects()
            console.print(f"[green]✓[/green] Found {len(projects)} project(s)")
            if projects:
                for proj in projects[:3]:  # Show first 3
                    console.print(f"    • {proj.name}")
                if len(projects) > 3:
                    console.print(f"    ... and {len(projects) - 3} more")

            # Get models
            models = client.get_all_lookml_models()
            console.print(f"[green]✓[/green] Found {len(models)} LookML model(s)")
            if models:
                for model in models[:3]:  # Show first 3
                    console.print(f"    • {model.name}")
                if len(models) > 3:
                    console.print(f"    ... and {len(models) - 3} more")

        console.print("\n[green bold]✓ All tests passed![/green bold]\n")

    except Exception as e:
        console.print(f"\n[red]✗ Test failed:[/red] {e}\n")
        console.print("[yellow]Troubleshooting tips:[/yellow]")
        console.print("  • Make sure you sourced the .env file: source .env")
        console.print("  • Verify LOOKERSDK_BASE_URL is correct")
        console.print("  • Check that credentials are correct")
        console.print("  • Verify network connectivity to Looker instance\n")
        sys.exit(1)


@cli.command("mcp")
@click.option(
    "--transport",
    "-t",
    type=click.Choice(["stdio", "sse", "streamable-http"]),
    default="stdio",
    help="Transport protocol to use",
)
def mcp_server(transport: str) -> None:
    """
    Start the MCP (Model Context Protocol) server.

    This exposes Looker CLI functionality as tools for AI agents via MCP.
    The server communicates over stdio by default and can be used with
    Claude Desktop or other MCP clients.

    Example usage:
      ./looker.py mcp                    # Start with stdio transport
      ./looker.py mcp --transport sse    # Start with SSE transport

    For Claude Desktop integration, add to your claude_desktop_config.json:
      {
        "mcpServers": {
          "looker": {
            "command": "/path/to/looker.py",
            "args": ["mcp"]
          }
        }
      }
    """
    from lookerctl.mcp_server import run_server

    try:
        console.print(f"\n[bold]Starting Looker MCP Server ({transport} transport)...[/bold]\n")
        run_server(transport)
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Server stopped by user[/yellow]\n")
    except Exception as e:
        console.print(f"\n[red]Server error:[/red] {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    cli()
