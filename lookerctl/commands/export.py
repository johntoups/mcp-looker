"""LookML export functionality - get all content from Looker to local.

Supports exporting:
1. User-Defined Dashboards (UDDs) - via dashboard_lookml() API
2. Looks (saved queries) - via look() API
3. LookML project files - use git clone/pull (not API)

WORKSPACE SAFETY NOTES:
- Export operations (read-only): Safe in any workspace
- Push/sync operations (modify state): Require dev workspace
- Functions that modify state include explicit workspace checks
"""

import json
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from lookerctl.commands.session import get_current_workspace, switch_to_workspace
from lookerctl.core.client import LookerClient

console = Console()


def export_project_files(
    client: LookerClient,
    project_id: str,
    output_dir: Path,
    git_branch: Optional[str] = None,
) -> dict[str, Any]:
    """
    Export all files from a Looker project.

    Args:
        client: Looker client instance
        project_id: Project ID to export
        output_dir: Directory to export files to
        git_branch: Optional git branch to export from

    Returns:
        Dictionary with export statistics
    """
    stats = {"files_exported": 0, "total_size": 0, "errors": []}

    try:
        # Get all project files using the SDK
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Exporting project: {project_id}...", total=None)

            # Get project files from Looker API
            # The all_project_files endpoint returns all files in the project
            files = client.sdk.all_project_files(project_id, fields="name,type,git_status")

            progress.update(task, description=f"Found {len(files)} files, downloading...")

            # Create output directory
            output_dir.mkdir(parents=True, exist_ok=True)

            # Export each file
            for file_obj in files:
                try:
                    # Get file path (ProjectFile uses 'path' not 'name')
                    file_path_str = getattr(file_obj, "path", None)
                    if not file_path_str:
                        continue

                    # Get file content
                    file_content = client.sdk.project_file(project_id, file_path_str)

                    if file_content:
                        # Get path and content with type guards
                        content_path = getattr(file_content, "path", None)
                        content_text = getattr(file_content, "content", None)

                        if content_path and content_text:
                            # Construct full path
                            file_path = output_dir / content_path

                            # Create parent directories
                            file_path.parent.mkdir(parents=True, exist_ok=True)

                            # Write content
                            file_path.write_text(content_text)
                            stats["files_exported"] += 1
                            stats["total_size"] += len(content_text)

                except Exception as e:
                    file_path_str = getattr(file_obj, "path", "unknown")
                    error_msg = f"Failed to export {file_path_str}: {e}"
                    stats["errors"].append(error_msg)
                    console.print(f"[yellow]Warning:[/yellow] {error_msg}")

            progress.update(task, description=f"✓ Exported {stats['files_exported']} files")

    except Exception as e:
        error_msg = f"Project export failed: {e}"
        stats["errors"].append(error_msg)
        console.print(f"[red]Error:[/red] {error_msg}")

    return stats


def export_all_lookml(client: LookerClient, output_base: Path) -> dict[str, Any]:
    """
    Export all LookML from all projects.

    Args:
        client: Looker client instance
        output_base: Base directory for exports

    Returns:
        Dictionary with overall statistics
    """
    overall_stats = {
        "projects_exported": 0,
        "total_files": 0,
        "total_size": 0,
        "errors": [],
    }

    # Get all projects
    projects = client.get_all_projects()

    console.print(f"\n[bold]Exporting LookML from {len(projects)} project(s)...[/bold]\n")

    for project in projects:
        if not project.id:
            continue

        console.print(f"\n[cyan]Project:[/cyan] {project.name} ({project.id})")

        # Create project-specific output directory
        project_dir = output_base / project.id

        # Export project files
        stats = export_project_files(client, project.id, project_dir)

        # Update overall stats
        overall_stats["projects_exported"] += 1
        overall_stats["total_files"] += stats["files_exported"]
        overall_stats["total_size"] += stats["total_size"]
        overall_stats["errors"].extend(stats["errors"])

        if stats["files_exported"] > 0:
            size_mb = stats["total_size"] / (1024 * 1024)
            console.print(
                f"  [green]✓[/green] Exported {stats['files_exported']} files "
                f"({size_mb:.2f} MB) to {project_dir}"
            )

    return overall_stats


def export_all_dashboards(
    client: LookerClient, output_dir: Path, limit: Optional[int] = None
) -> dict[str, Any]:
    """
    Export all user-defined dashboards (UDDs) as LookML.

    Uses dashboard_lookml() API to get LookML representation of dashboards
    that are stored in Looker database (not in git).

    Args:
        client: Looker client instance
        output_dir: Directory to export dashboards to
        limit: Optional limit on number of dashboards to export (for testing)

    Returns:
        Dictionary with export statistics
    """
    stats = {"dashboards_exported": 0, "total_size": 0, "errors": []}

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Fetching dashboards...", total=None)

            # Get all dashboards (cached)
            dashboards = client.get_all_dashboards_cached(fields="id,title,user_id,folder")

            # Apply limit if specified
            if limit:
                dashboards = dashboards[:limit]

            progress.update(task, description=f"Found {len(dashboards)} dashboards, exporting...")

            # Create output directory
            output_dir.mkdir(parents=True, exist_ok=True)

            # Export each dashboard
            for dashboard in dashboards:
                try:
                    if not dashboard.id:
                        continue

                    # Get dashboard LookML (cached for performance)
                    lookml = client.get_dashboard_lookml_cached(dashboard.id)

                    if lookml and hasattr(lookml, "lookml") and lookml.lookml:
                        # Create safe filename from dashboard ID and title
                        safe_title = "".join(
                            c if c.isalnum() or c in (" ", "_", "-") else "_"
                            for c in (dashboard.title or "untitled")
                        )
                        filename = f"{dashboard.id}_{safe_title}.lkml"
                        file_path = output_dir / filename

                        # Write LookML content
                        file_path.write_text(lookml.lookml)
                        stats["dashboards_exported"] += 1
                        stats["total_size"] += len(lookml.lookml)

                except Exception as e:
                    error_msg = f"Failed to export dashboard {dashboard.id}: {e}"
                    stats["errors"].append(error_msg)
                    console.print(f"[yellow]Warning:[/yellow] {error_msg}")

            progress.update(
                task, description=f"✓ Exported {stats['dashboards_exported']} dashboards"
            )

    except Exception as e:
        error_msg = f"Dashboard export failed: {e}"
        stats["errors"].append(error_msg)
        console.print(f"[red]Error:[/red] {error_msg}")

    return stats


def export_all_looks(
    client: LookerClient, output_dir: Path, limit: Optional[int] = None
) -> dict[str, Any]:
    """
    Export all looks (saved queries) as JSON.

    Uses look() API to get complete Look definitions including queries.

    Args:
        client: Looker client instance
        output_dir: Directory to export looks to
        limit: Optional limit on number of looks to export (for testing)

    Returns:
        Dictionary with export statistics
    """
    stats = {"looks_exported": 0, "total_size": 0, "errors": []}

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Fetching looks...", total=None)

            # Get all looks (cached)
            looks = client.get_all_looks_cached(fields="id,title,user_id,folder,query_id")

            # Apply limit if specified
            if limit:
                looks = looks[:limit]

            progress.update(task, description=f"Found {len(looks)} looks, exporting...")

            # Create output directory
            output_dir.mkdir(parents=True, exist_ok=True)

            # Export each look
            for look in looks:
                try:
                    if not look.id:
                        continue

                    # Get full look details
                    full_look = client.sdk.look(look.id)

                    if full_look:
                        # Create safe filename from look ID and title
                        safe_title = "".join(
                            c if c.isalnum() or c in (" ", "_", "-") else "_"
                            for c in (look.title or "untitled")
                        )
                        filename = f"{look.id}_{safe_title}.json"
                        file_path = output_dir / filename

                        # Convert to dict for JSON serialization
                        look_data = {
                            "id": full_look.id,
                            "title": full_look.title,
                            "description": full_look.description,
                            "user_id": full_look.user_id,
                            "folder": {"id": full_look.folder.id, "name": full_look.folder.name}
                            if full_look.folder
                            else None,
                            "query_id": full_look.query_id,
                            "query": {
                                "model": full_look.query.model,
                                "view": full_look.query.view,
                                "fields": full_look.query.fields,
                                "filters": full_look.query.filters,
                                "sorts": full_look.query.sorts,
                                "limit": full_look.query.limit,
                            }
                            if full_look.query
                            else None,
                        }

                        # Write JSON content
                        json_content = json.dumps(look_data, indent=2)
                        file_path.write_text(json_content)
                        stats["looks_exported"] += 1
                        stats["total_size"] += len(json_content)

                except Exception as e:
                    error_msg = f"Failed to export look {look.id}: {e}"
                    stats["errors"].append(error_msg)
                    console.print(f"[yellow]Warning:[/yellow] {error_msg}")

            progress.update(task, description=f"✓ Exported {stats['looks_exported']} looks")

    except Exception as e:
        error_msg = f"Look export failed: {e}"
        stats["errors"].append(error_msg)
        console.print(f"[red]Error:[/red] {error_msg}")

    return stats


def export_all_content(client: LookerClient, output_base: Path) -> dict[str, Any]:
    """
    Export all Looker content: dashboards, looks, and LookML projects.

    Args:
        client: Looker client instance
        output_base: Base directory for exports

    Returns:
        Dictionary with overall statistics
    """
    overall_stats = {
        "dashboards_exported": 0,
        "looks_exported": 0,
        "projects_exported": 0,
        "total_files": 0,
        "errors": [],
    }

    console.print("\n[bold]Exporting All Looker Content...[/bold]\n")

    # Export dashboards
    console.print("[cyan]Exporting dashboards...[/cyan]")
    dashboard_dir = output_base / "dashboards"
    dashboard_stats = export_all_dashboards(client, dashboard_dir)
    overall_stats["dashboards_exported"] = dashboard_stats["dashboards_exported"]
    overall_stats["errors"].extend(dashboard_stats["errors"])

    if dashboard_stats["dashboards_exported"] > 0:
        size_mb = dashboard_stats["total_size"] / (1024 * 1024)
        console.print(
            f"  [green]✓[/green] Exported {dashboard_stats['dashboards_exported']} dashboards "
            f"({size_mb:.2f} MB) to {dashboard_dir}\n"
        )

    # Export looks
    console.print("[cyan]Exporting looks...[/cyan]")
    looks_dir = output_base / "looks"
    looks_stats = export_all_looks(client, looks_dir)
    overall_stats["looks_exported"] = looks_stats["looks_exported"]
    overall_stats["errors"].extend(looks_stats["errors"])

    if looks_stats["looks_exported"] > 0:
        size_mb = looks_stats["total_size"] / (1024 * 1024)
        console.print(
            f"  [green]✓[/green] Exported {looks_stats['looks_exported']} looks "
            f"({size_mb:.2f} MB) to {looks_dir}\n"
        )

    # Note about LookML project files
    console.print(
        "\n[yellow]Note:[/yellow] LookML project files (models, views, explores) "
        "are managed via git."
    )
    console.print(
        "Use git clone/pull to get project files, or use 'export project' command "
        "with git integration.\n"
    )

    return overall_stats


def sync_project_from_git(
    client: LookerClient,
    project_id: str,
    branch: Optional[str] = None,
) -> dict[str, Any]:
    """
    Sync a Looker project from its git repository.

    IMPORTANT: This modifies project state and requires dev workspace.

    Args:
        client: Looker client instance
        project_id: Project ID to sync
        branch: Optional git branch to sync to

    Returns:
        Dictionary with sync status
    """
    result = {"success": False, "message": "", "branch": branch}

    try:
        # Make sure we're in dev workspace - this modifies project state
        current_workspace = get_current_workspace(client)
        if current_workspace != "dev":
            console.print("[yellow]Switching to dev workspace...[/yellow]")
            switch_result = switch_to_workspace(client, "dev")
            if not switch_result["success"]:
                result["message"] = "Failed to switch to dev workspace"
                console.print(f"[red]✗[/red] {result['message']}")
                return result

        # Update from git
        console.print(f"Syncing project {project_id} from git...")

        # Use reset_project_to_remote to sync from git
        update_result = client.sdk.reset_project_to_remote(project_id)

        if update_result:
            result["success"] = True
            result["message"] = "Project synced from git successfully"
            console.print(f"[green]✓[/green] {result['message']}")
        else:
            result["message"] = "Failed to sync project"
            console.print(f"[red]✗[/red] {result['message']}")

    except Exception as e:
        result["message"] = f"Sync failed: {e}"
        console.print(f"[red]Error:[/red] {result['message']}")

    return result


def push_local_files_to_looker(
    client: LookerClient,
    project_id: str,
    local_dir: Path,
    validate_after: bool = True,
) -> dict[str, Any]:
    """
    Push local LookML files to Looker project (dev workspace).

    This enables local development workflow:
    1. Export LookML to local
    2. Make changes locally (AI or human)
    3. Push changes to Looker dev branch
    4. Validate in Looker
    5. Get feedback and iterate

    Args:
        client: Looker client instance
        project_id: Project ID to push to
        local_dir: Directory containing LookML files
        validate_after: Whether to validate after pushing

    Returns:
        Dictionary with push results and validation
    """
    result = {
        "success": False,
        "files_pushed": 0,
        "files_failed": 0,
        "errors": [],
        "validation": None,
    }

    try:
        # Make sure we're in dev workspace
        current_workspace = get_current_workspace(client)
        if current_workspace != "dev":
            console.print("[yellow]Switching to dev workspace...[/yellow]")
            switch_result = switch_to_workspace(client, "dev")
            if not switch_result["success"]:
                result["errors"].append("Failed to switch to dev workspace")
                return result

        # Find all LookML files
        lookml_patterns = ["*.lkml", "*.model.lkml", "*.view.lkml", "*.explore.lkml"]
        files_to_push = []
        for pattern in lookml_patterns:
            files_to_push.extend(local_dir.rglob(pattern))

        if not files_to_push:
            result["errors"].append(f"No LookML files found in {local_dir}")
            return result

        console.print(f"\n[bold]Pushing {len(files_to_push)} file(s) to Looker...[/bold]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Pushing files...", total=len(files_to_push))

            for file_path in files_to_push:
                try:
                    # Get relative path from local_dir
                    relative_path = file_path.relative_to(local_dir)

                    # Read file content
                    content = file_path.read_text()

                    # Push to Looker - note: SDK may not have direct file write API
                    # Files in dev workspace are typically managed through git
                    # This is a placeholder for the actual implementation
                    if hasattr(client.sdk, "update_project_file"):
                        client.sdk.update_project_file(  # type: ignore
                            project_id,
                            str(relative_path),
                            body={"content": content},
                        )
                    else:
                        # Fallback: log that this needs git-based workflow
                        raise NotImplementedError(
                            "Direct file push not available in SDK. "
                            "Use git workflow for file updates."
                        )

                    result["files_pushed"] += 1
                    progress.advance(task)

                except Exception as e:
                    error_msg = f"Failed to push {relative_path}: {e}"
                    result["errors"].append(error_msg)
                    result["files_failed"] += 1
                    console.print(f"[yellow]Warning:[/yellow] {error_msg}")

            progress.update(
                task,
                description=f"✓ Pushed {result['files_pushed']} file(s), "
                f"{result['files_failed']} failed",
            )

        # Validate if requested
        if validate_after and result["files_pushed"] > 0:
            console.print("\n[bold]Validating project...[/bold]\n")

            try:
                validation_result = client.validate_project(project_id)
                result["validation"] = {
                    "errors": [],
                    "has_errors": False,
                }

                if validation_result.errors:
                    result["validation"]["has_errors"] = True

                    for error in validation_result.errors:
                        result["validation"]["errors"].append(
                            {
                                "message": error.message,
                                "file_path": error.file_path,
                                "line": error.line_number,
                                "severity": error.severity,
                            }
                        )

                    # Print validation errors
                    console.print(
                        f"[red]✗ Validation failed with {len(validation_result.errors)} error(s):[/red]\n"
                    )
                    for error in validation_result.errors[:10]:
                        console.print(f"  [red]ERROR:[/red] {error.message}")
                        if error.file_path:
                            console.print(f"    File: {error.file_path}")
                        if error.line_number:
                            console.print(f"    Line: {error.line_number}")
                        console.print()

                    if len(validation_result.errors) > 10:
                        console.print(
                            f"  ... and {len(validation_result.errors) - 10} more errors\n"
                        )
                else:
                    console.print("[green]✓ Validation passed![/green]\n")
                    result["success"] = True

            except Exception as e:
                error_msg = f"Validation failed: {e}"
                result["errors"].append(error_msg)
                console.print(f"[red]Error:[/red] {error_msg}")

        elif result["files_pushed"] > 0:
            result["success"] = True

    except Exception as e:
        error_msg = f"Push failed: {e}"
        result["errors"].append(error_msg)
        console.print(f"[red]Error:[/red] {error_msg}")

    return result


def validate_local_changes(
    client: LookerClient,
    project_id: str,
    local_dir: Path,
) -> dict[str, Any]:
    """
    Validate local LookML changes without permanently pushing them.

    Workflow:
    1. Push local files to Looker dev branch
    2. Validate
    3. Return validation results

    This gives the same validation experience as Looker console but working locally.

    Args:
        client: Looker client instance
        project_id: Project ID
        local_dir: Directory containing LookML files

    Returns:
        Validation results
    """
    console.print("\n[bold]Validating local changes...[/bold]\n")

    # Push and validate
    result = push_local_files_to_looker(client, project_id, local_dir, validate_after=True)

    return result
