"""LookML usage analysis functionality - track explore/field usage."""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from lookerctl.core.client import LookerClient

console = Console()


def analyze_specific_dashboards(client: LookerClient, dashboard_ids: list[str]) -> dict[str, Any]:
    """
    Analyze explore and field usage for specific dashboards only.

    This is the scoped alternative to analyze_all_usage - only fetches
    the dashboards you specify, making it much faster for targeted analysis.

    Args:
        client: Looker client instance
        dashboard_ids: List of dashboard IDs to analyze

    Returns:
        Dictionary with usage analysis for the specified dashboards
    """
    usage_map: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    stats = {
        "dashboards_requested": len(dashboard_ids),
        "dashboards_analyzed": 0,
        "dashboards_failed": 0,
        "explores_found": set(),
        "errors": [],
    }

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Analyzing {len(dashboard_ids)} dashboard(s)...", total=len(dashboard_ids)
            )

            for dashboard_id in dashboard_ids:
                try:
                    # Get full dashboard details including elements (cached)
                    full_dashboard = client.get_dashboard_cached(
                        dashboard_id, fields="id,title,dashboard_elements"
                    )

                    if not full_dashboard.dashboard_elements:
                        progress.advance(task)
                        continue

                    # Analyze each dashboard element
                    for element in full_dashboard.dashboard_elements:
                        if not element.query or not element.query.id:
                            continue

                        try:
                            # Get the query details - CACHED for performance
                            query = client.get_query_cached(element.query.id)

                            if query.model and query.view:
                                explore_key = f"{query.model}.{query.view}"
                                stats["explores_found"].add(explore_key)

                                # Track fields used in this query
                                fields_used = []
                                if query.fields:
                                    fields_used.extend(query.fields)
                                if query.pivots:
                                    fields_used.extend(query.pivots)
                                if query.filters:
                                    fields_used.extend(query.filters.keys())

                                # Add to usage map
                                for field in fields_used:
                                    usage_map[explore_key][field].add(
                                        f"Dashboard: {full_dashboard.title} ({dashboard_id})"
                                    )

                        except Exception:
                            # Query might not exist or be accessible
                            pass

                    stats["dashboards_analyzed"] += 1

                except Exception as e:
                    error_msg = f"Failed to analyze dashboard {dashboard_id}: {e}"
                    stats["errors"].append(error_msg)
                    stats["dashboards_failed"] += 1

                finally:
                    progress.advance(task)

            progress.update(
                task,
                description=f"✓ Analyzed {stats['dashboards_analyzed']}/{len(dashboard_ids)} dashboards, "
                f"found {len(stats['explores_found'])} explores",
                refresh=True,
            )

    except Exception as e:
        error_msg = f"Dashboard analysis failed: {e}"
        stats["errors"].append(error_msg)
        console.print(f"[red]Error:[/red] {error_msg}")

    return {"usage_map": usage_map, "stats": stats}


def find_dashboards_using_explore(client: LookerClient, explore_key: str) -> dict[str, Any]:
    """
    Find all dashboards that use a specific explore (metadata only, fast).

    This only fetches dashboard IDs and titles, not full details,
    making it very fast even with 15K+ dashboards. Use this to identify
    candidates before doing deep analysis.

    Args:
        client: Looker client instance
        explore_key: Explore key in "model.explore" format (e.g., "hub.CE_aws")

    Returns:
        Dictionary with:
        - dashboards: List of {id, title} dicts for matching dashboards
        - total_dashboards_checked: Total dashboards examined
        - total_matches: Number of dashboards using this explore
    """
    # Parse explore key
    if "." not in explore_key:
        raise ValueError(f"Explore key must be in 'model.explore' format, got: {explore_key}")

    model, explore = explore_key.split(".", 1)

    matching_dashboards = []
    stats = {"total_dashboards_checked": 0, "total_matches": 0, "errors": []}

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            # Get all dashboards (cached, metadata only)
            dashboards = client.get_all_dashboards_cached(fields="id,title")
            task = progress.add_task(
                f"Checking {len(dashboards)} dashboards for {explore_key}...",
                total=len(dashboards),
            )

            stats["total_dashboards_checked"] = len(dashboards)

            for dashboard in dashboards:
                try:
                    if not dashboard.id:
                        progress.advance(task)
                        continue

                    # Get dashboard elements to check queries
                    full_dashboard = client.get_dashboard_cached(
                        dashboard.id, fields="id,title,dashboard_elements"
                    )

                    if not full_dashboard.dashboard_elements:
                        progress.advance(task)
                        continue

                    # Check if any element uses this explore
                    for element in full_dashboard.dashboard_elements:
                        if not element.query or not element.query.id:
                            continue

                        try:
                            query = client.get_query_cached(element.query.id)

                            if query.model == model and query.view == explore:
                                # Found a match!
                                matching_dashboards.append({
                                    "id": dashboard.id,
                                    "title": full_dashboard.title or "Untitled",
                                })
                                stats["total_matches"] += 1
                                # Don't need to check other elements in this dashboard
                                break

                        except Exception:
                            # Query might not exist
                            pass

                except Exception as e:
                    error_msg = f"Failed to check dashboard {dashboard.id}: {e}"
                    stats["errors"].append(error_msg)

                finally:
                    progress.advance(task)

            progress.update(
                task,
                description=f"✓ Found {stats['total_matches']} dashboard(s) using {explore_key}",
                refresh=True,
            )

    except Exception as e:
        error_msg = f"Search failed: {e}"
        stats["errors"].append(error_msg)
        console.print(f"[red]Error:[/red] {error_msg}")

    return {"dashboards": matching_dashboards, **stats}


def trace_field_usage(client: LookerClient, field_name: str) -> dict[str, Any]:
    """
    Trace usage of a specific field across all dashboards and looks.

    This is a surgical alternative to analyze_all_usage - only tracks one field
    instead of analyzing everything. Uses smart filtering to minimize API calls.

    Args:
        client: Looker client instance
        field_name: Field name to trace (e.g., "aws_cost.total_cost", "users.count")

    Returns:
        Dictionary with:
        - field_name: The field being traced
        - dashboards: List of {id, title, explore, queries} using this field
        - looks: List of {id, title, explore} using this field
        - total_dashboard_usage: Count of dashboards using this field
        - total_look_usage: Count of looks using this field
        - total_usage: Total usage count
    """
    dashboards_using_field = []
    looks_using_field = []
    stats = {
        "dashboards_checked": 0,
        "looks_checked": 0,
        "queries_analyzed": 0,
        "errors": [],
    }

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            # Check dashboards
            dashboards = client.get_all_dashboards_cached(fields="id,title")
            dashboard_task = progress.add_task(
                f"Checking {len(dashboards)} dashboards for '{field_name}'...",
                total=len(dashboards),
            )

            for dashboard in dashboards:
                try:
                    if not dashboard.id:
                        progress.advance(dashboard_task)
                        continue

                    stats["dashboards_checked"] += 1

                    # Get dashboard elements
                    full_dashboard = client.get_dashboard_cached(
                        dashboard.id, fields="id,title,dashboard_elements"
                    )

                    if not full_dashboard.dashboard_elements:
                        progress.advance(dashboard_task)
                        continue

                    # Track queries using this field in this dashboard
                    matching_queries = []

                    for element in full_dashboard.dashboard_elements:
                        if not element.query or not element.query.id:
                            continue

                        try:
                            stats["queries_analyzed"] += 1
                            query = client.get_query_cached(element.query.id)

                            # Check if this query uses the field
                            fields_in_query = []
                            if query.fields:
                                fields_in_query.extend(query.fields)
                            if query.pivots:
                                fields_in_query.extend(query.pivots)
                            if query.filters:
                                fields_in_query.extend(query.filters.keys())

                            if field_name in fields_in_query:
                                matching_queries.append({
                                    "query_id": element.query.id,
                                    "explore": f"{query.model}.{query.view}"
                                    if query.model and query.view
                                    else "unknown",
                                })

                        except Exception:
                            # Query might not exist
                            pass

                    # If any queries use this field, add dashboard to results
                    if matching_queries:
                        # Get unique explores
                        explores = list({q["explore"] for q in matching_queries})

                        dashboards_using_field.append({
                            "id": dashboard.id,
                            "title": full_dashboard.title or "Untitled",
                            "explores": explores,
                            "query_count": len(matching_queries),
                        })

                except Exception as e:
                    error_msg = f"Failed to check dashboard {dashboard.id}: {e}"
                    stats["errors"].append(error_msg)

                finally:
                    progress.advance(dashboard_task)

            progress.update(
                dashboard_task,
                description=f"✓ Found {len(dashboards_using_field)} dashboard(s) using '{field_name}'",
                refresh=True,
            )

            # Check looks
            looks = client.get_all_looks_cached(fields="id,title,query_id")
            look_task = progress.add_task(
                f"Checking {len(looks)} looks for '{field_name}'...", total=len(looks)
            )

            for look in looks:
                try:
                    if not look.query_id:
                        progress.advance(look_task)
                        continue

                    stats["looks_checked"] += 1

                    # Get query details
                    query = client.get_query_cached(look.query_id)

                    # Check if this query uses the field
                    fields_in_query = []
                    if query.fields:
                        fields_in_query.extend(query.fields)
                    if query.pivots:
                        fields_in_query.extend(query.pivots)
                    if query.filters:
                        fields_in_query.extend(query.filters.keys())

                    if field_name in fields_in_query:
                        looks_using_field.append({
                            "id": look.id,
                            "title": look.title or "Untitled",
                            "explore": f"{query.model}.{query.view}"
                            if query.model and query.view
                            else "unknown",
                        })

                except Exception as e:
                    error_msg = f"Failed to check look {look.id}: {e}"
                    stats["errors"].append(error_msg)

                finally:
                    progress.advance(look_task)

            progress.update(
                look_task,
                description=f"✓ Found {len(looks_using_field)} look(s) using '{field_name}'",
                refresh=True,
            )

    except Exception as e:
        error_msg = f"Field trace failed: {e}"
        stats["errors"].append(error_msg)
        console.print(f"[red]Error:[/red] {error_msg}")

    return {
        "field_name": field_name,
        "dashboards": dashboards_using_field,
        "looks": looks_using_field,
        "total_dashboard_usage": len(dashboards_using_field),
        "total_look_usage": len(looks_using_field),
        "total_usage": len(dashboards_using_field) + len(looks_using_field),
        "stats": stats,
    }


def analyze_dashboard_usage(client: LookerClient) -> dict[str, Any]:
    """
    Analyze explore and field usage across dashboards in known accounts.

    Args:
        client: Looker client instance

    Returns:
        Dictionary mapping explores to fields used in dashboards
    """
    usage_map: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    stats = {
        "dashboards_analyzed": 0,
        "dashboards_skipped": 0,
        "explores_found": set(),
        "errors": [],
    }

    try:
        with (
            Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                console=console,
            ) as progress,
            ThreadPoolExecutor() as executor,
        ):
            # Get known account folder IDs
            known_folder_ids = list_all_folders(client)
            console.print(f"[dim]Found {len(known_folder_ids)} folders[/dim]")

            # Get all dashboards (cached) with folder info
            all_dashboards = client.get_all_dashboards_cached(fields="id,title,folder")

            # Filter to only dashboards in known account folders
            dashboards = [
                d
                for d in all_dashboards
                if d.folder and d.folder.id and d.folder.id in known_folder_ids
            ]

            console.print(
                f"[dim]Filtered to {len(dashboards)} dashboards (from {len(all_dashboards)} total)[/dim]"
            )

            task = progress.add_task(
                f"Analyzing {len(dashboards)} dashboards in known accounts...",
                total=len(dashboards),
            )

            def _process():
                try:
                    # Get full dashboard details including elements
                    if not dashboard.id:
                        return

                    # Use cached method - CRITICAL for performance with 15K dashboards
                    full_dashboard = client.get_dashboard_cached(
                        dashboard.id, fields="id,title,dashboard_elements"
                    )

                    if not full_dashboard.dashboard_elements:
                        return

                    # Analyze each dashboard element
                    for element in full_dashboard.dashboard_elements:
                        if not element.query or not element.query.id:
                            return

                        try:
                            # Get the query details - CACHED for performance
                            query = client.get_query_cached(element.query.id)

                            if query.model and query.view:
                                explore_key = f"{query.model}.{query.view}"
                                stats["explores_found"].add(explore_key)

                                # Track fields used in this query
                                fields_used = []
                                if query.fields:
                                    fields_used.extend(query.fields)
                                if query.pivots:
                                    fields_used.extend(query.pivots)
                                if query.filters:
                                    fields_used.extend(query.filters.keys())

                                # Add to usage map
                                for field in fields_used:
                                    usage_map[explore_key][field].add(
                                        f"Dashboard: {full_dashboard.title} ({dashboard.id})"
                                    )

                        except Exception:
                            # Query might not exist or be accessible
                            return

                    stats["dashboards_analyzed"] += 1

                except Exception as e:
                    error_msg = f"Failed to analyze dashboard {dashboard.id}: {e}"
                    stats["errors"].append(error_msg)

                finally:
                    progress.advance(task)

            for dashboard in dashboards:
                executor.submit(_process)

            executor.shutdown(wait=True)

            progress.update(
                task,
                description=f"✓ Analyzed {stats['dashboards_analyzed']} dashboards, "
                f"found {len(stats['explores_found'])} explores",
                refresh=True,
            )

    except Exception as e:
        error_msg = f"Dashboard analysis failed: {e}"
        stats["errors"].append(error_msg)
        console.print(f"[red]Error:[/red] {error_msg}")

    return {"usage_map": usage_map, "stats": stats}


def analyze_look_usage(client: LookerClient) -> dict[str, Any]:
    """
    Analyze explore and field usage across looks in known folders.

    Only analyzes looks in folders belonging to the known folder names
    defined in constants.KNOWN_FOLDER_NAMES.

    Args:
        client: Looker client instance

    Returns:
        Dictionary mapping explores to fields used in looks
    """
    usage_map: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    stats = {"looks_analyzed": 0, "looks_skipped": 0, "explores_found": set(), "errors": []}

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Analyzing looks in known accounts...", total=None)

            # Get known folder IDs
            known_folder_ids = list_all_folders(client)

            # Get all looks (cached) with folder info
            all_looks = client.get_all_looks_cached(fields="id,title,query_id,folder")

            # Filter to only looks in known account folders
            looks = [
                look
                for look in all_looks
                if look.folder and look.folder.id and look.folder.id in known_folder_ids
            ]

            progress.update(
                task,
                description=f"Found {len(looks)} looks in known folders (from {len(all_looks)} total), analyzing...",
            )

            for look in looks:
                try:
                    if not look.query_id:
                        continue

                    # Get the query details - CACHED for performance
                    query = client.get_query_cached(look.query_id)

                    if query.model and query.view:
                        explore_key = f"{query.model}.{query.view}"
                        stats["explores_found"].add(explore_key)

                        # Track fields used in this query
                        fields_used = []
                        if query.fields:
                            fields_used.extend(query.fields)
                        if query.pivots:
                            fields_used.extend(query.pivots)
                        if query.filters:
                            fields_used.extend(query.filters.keys())

                        # Add to usage map
                        for field in fields_used:
                            usage_map[explore_key][field].add(f"Look: {look.title} ({look.id})")

                    stats["looks_analyzed"] += 1

                except Exception as e:
                    error_msg = f"Failed to analyze look {look.id}: {e}"
                    stats["errors"].append(error_msg)

            progress.update(
                task,
                description=f"✓ Analyzed {stats['looks_analyzed']} looks, "
                f"found {len(stats['explores_found'])} explores",
            )

    except Exception as e:
        error_msg = f"Look analysis failed: {e}"
        stats["errors"].append(error_msg)
        console.print(f"[red]Error:[/red] {error_msg}")

    return {"usage_map": usage_map, "stats": stats}


def analyze_all_usage(client: LookerClient) -> dict[str, Any]:
    """
    Analyze explore and field usage across dashboards and looks in known folders.

    Only analyzes content in folders belonging to the known folder names
    defined in constants.KNOWN_FOLDER_NAMES. This scoping dramatically reduces
    analysis time by focusing on meaningful folders.

    Args:
        client: Looker client instance

    Returns:
        Comprehensive usage analysis for known folders
    """
    console.print("\n[bold]Analyzing LookML Usage (Known Folders Only)...[/bold]\n")

    # Analyze dashboards
    dashboard_result = analyze_dashboard_usage(client)

    # Analyze looks
    look_result = analyze_look_usage(client)

    # Combine results
    combined_usage: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    for explore_key, fields in dashboard_result["usage_map"].items():
        for field, locations in fields.items():
            combined_usage[explore_key][field].update(locations)

    for explore_key, fields in look_result["usage_map"].items():
        for field, locations in fields.items():
            combined_usage[explore_key][field].update(locations)

    return {
        "usage_map": combined_usage,
        "dashboard_stats": dashboard_result["stats"],
        "look_stats": look_result["stats"],
        "total_explores": len(combined_usage),
    }


def print_usage_summary(analysis: dict[str, Any]) -> None:
    """
    Print a summary of usage analysis.

    Args:
        analysis: Analysis results from analyze_all_usage
    """
    console.print("\n[bold]Usage Analysis Summary[/bold]\n")

    # Print stats
    console.print(f"Dashboards analyzed: {analysis['dashboard_stats']['dashboards_analyzed']}")
    console.print(f"Looks analyzed: {analysis['look_stats']['looks_analyzed']}")
    console.print(f"Total explores found: {analysis['total_explores']}")

    # Print top explores by field usage
    usage_counts = []
    for explore_key, fields in analysis["usage_map"].items():
        total_fields = len(fields)
        total_usage = sum(len(locations) for locations in fields.values())
        usage_counts.append((explore_key, total_fields, total_usage))

    usage_counts.sort(key=lambda x: x[2], reverse=True)

    if usage_counts:
        console.print("\n[bold]Top Explores by Usage:[/bold]\n")
        table = Table()
        table.add_column("Explore", style="cyan")
        table.add_column("Fields Used", justify="right")
        table.add_column("Total References", justify="right")

        for explore_key, field_count, usage_count in usage_counts[:10]:
            table.add_row(explore_key, str(field_count), str(usage_count))

        console.print(table)


def export_usage_analysis(analysis: dict[str, Any], output_file: Path) -> None:
    """
    Export usage analysis to a JSON file.

    Args:
        analysis: Analysis results from analyze_all_usage
        output_file: Output file path
    """
    import json

    # Convert sets to lists for JSON serialization
    export_data = {
        "usage_map": {
            explore_key: {field: list(locations) for field, locations in fields.items()}
            for explore_key, fields in analysis["usage_map"].items()
        },
        "dashboard_stats": {
            "dashboards_analyzed": analysis["dashboard_stats"]["dashboards_analyzed"],
            "explores_found": list(analysis["dashboard_stats"]["explores_found"]),
            "error_count": len(analysis["dashboard_stats"]["errors"]),
        },
        "look_stats": {
            "looks_analyzed": analysis["look_stats"]["looks_analyzed"],
            "explores_found": list(analysis["look_stats"]["explores_found"]),
            "error_count": len(analysis["look_stats"]["errors"]),
        },
        "total_explores": analysis["total_explores"],
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(export_data, indent=2))

    console.print(f"\n[green]✓[/green] Exported usage analysis to {output_file}")


def get_explore_fields(client: LookerClient, model_name: str, explore_name: str) -> dict[str, Any]:
    """
    Get all available fields in an explore from Looker API.

    This returns the actual runtime schema - what fields are really available.

    Args:
        client: Looker client instance
        model_name: Model name
        explore_name: Explore name

    Returns:
        Dictionary with explore metadata and fields
    """
    try:
        # Get explore metadata from Looker API
        explore = client.sdk.lookml_model_explore(model_name, explore_name)

        fields_by_type = {
            "dimensions": [],
            "measures": [],
            "filters": [],
            "parameters": [],
        }

        # Extract dimensions
        if explore.fields and explore.fields.dimensions:
            for field in explore.fields.dimensions:
                fields_by_type["dimensions"].append({
                    "name": field.name,
                    "type": field.type,
                    "label": field.label,
                    "description": field.description,
                    "sql": field.sql,
                    "hidden": field.hidden or False,
                    "view": field.view_label,
                })

        # Extract measures
        if explore.fields and explore.fields.measures:
            for field in explore.fields.measures:
                fields_by_type["measures"].append({
                    "name": field.name,
                    "type": field.type,
                    "label": field.label,
                    "description": field.description,
                    "sql": field.sql,
                    "hidden": field.hidden or False,
                    "view": field.view_label,
                })

        # Extract filters
        if explore.fields and explore.fields.filters:
            for field in explore.fields.filters:
                fields_by_type["filters"].append({
                    "name": field.name,
                    "type": field.type,
                    "label": field.label,
                    "description": field.description,
                })

        # Extract parameters
        if explore.fields and explore.fields.parameters:
            for field in explore.fields.parameters:
                fields_by_type["parameters"].append({
                    "name": field.name,
                    "type": field.type,
                    "label": field.label,
                    "description": field.description,
                })

        return {
            "explore": f"{model_name}.{explore_name}",
            "label": explore.label,
            "description": explore.description,
            "fields": fields_by_type,
            "field_count": {
                "dimensions": len(fields_by_type["dimensions"]),
                "measures": len(fields_by_type["measures"]),
                "filters": len(fields_by_type["filters"]),
                "parameters": len(fields_by_type["parameters"]),
            },
        }

    except Exception as e:
        console.print(f"[red]Error getting explore fields:[/red] {e}")
        raise


def print_explore_fields(explore_data: dict[str, Any], show_hidden: bool = False) -> None:
    """
    Print explore fields in a readable format.

    Args:
        explore_data: Explore data from get_explore_fields
        show_hidden: Whether to show hidden fields
    """
    console.print(f"\n[bold]Explore: {explore_data['explore']}[/bold]")
    if explore_data.get("label"):
        console.print(f"Label: {explore_data['label']}")
    if explore_data.get("description"):
        console.print(f"Description: {explore_data['description']}")
    console.print()

    # Print field counts
    counts = explore_data["field_count"]
    console.print("[bold]Field Summary:[/bold]")
    console.print(f"  Dimensions: {counts['dimensions']}")
    console.print(f"  Measures: {counts['measures']}")
    console.print(f"  Filters: {counts['filters']}")
    console.print(f"  Parameters: {counts['parameters']}")
    console.print()

    # Print dimensions
    if explore_data["fields"]["dimensions"]:
        console.print("[bold cyan]Dimensions:[/bold cyan]\n")
        for field in explore_data["fields"]["dimensions"]:
            if not show_hidden and field.get("hidden"):
                continue

            hidden_marker = " [dim](hidden)[/dim]" if field.get("hidden") else ""
            console.print(f"  • [cyan]{field['name']}[/cyan]{hidden_marker}")

            if field.get("label"):
                console.print(f"    Label: {field['label']}")
            if field.get("type"):
                console.print(f"    Type: {field['type']}")
            if field.get("description"):
                console.print(f"    Description: {field['description']}")
            if field.get("view"):
                console.print(f"    View: {field['view']}")
            console.print()

    # Print measures
    if explore_data["fields"]["measures"]:
        console.print("[bold green]Measures:[/bold green]\n")
        for field in explore_data["fields"]["measures"]:
            if not show_hidden and field.get("hidden"):
                continue

            hidden_marker = " [dim](hidden)[/dim]" if field.get("hidden") else ""
            console.print(f"  • [green]{field['name']}[/green]{hidden_marker}")

            if field.get("label"):
                console.print(f"    Label: {field['label']}")
            if field.get("type"):
                console.print(f"    Type: {field['type']}")
            if field.get("description"):
                console.print(f"    Description: {field['description']}")
            if field.get("view"):
                console.print(f"    View: {field['view']}")
            console.print()


def find_unused_explores(client: LookerClient, analysis: dict[str, Any]) -> list[str]:
    """
    Find explores that exist in the instance but are not used in any dashboards or looks.

    Args:
        client: Looker client instance
        analysis: Analysis results from analyze_all_usage

    Returns:
        List of unused explore keys
    """
    used_explores = set(analysis["usage_map"].keys())
    all_explores = set()

    # Get all models and their explores
    models = client.get_all_lookml_models()
    for model in models:
        if model.explores:
            for explore in model.explores:
                explore_key = f"{model.name}.{explore.name}"
                all_explores.add(explore_key)

    unused = all_explores - used_explores
    return sorted(unused)


def list_all_explores(client: LookerClient) -> list[dict[str, Any]]:
    """
    List all available model.explore combinations in the Looker instance.

    This is helpful for discovering what explores exist and their correct names
    for use in baseline testing and golden tests.

    Args:
        client: Looker client instance

    Returns:
        List of explore dictionaries with model, explore, label, and description
    """
    explores_list = []

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Fetching models and explores...", total=None)

            # Get all models
            models = client.get_all_lookml_models()
            progress.update(task, description=f"Found {len(models)} models, fetching explores...")

            for model in models:
                if not model.name or not model.explores:
                    continue

                for explore in model.explores:
                    if not explore.name:
                        continue

                    explores_list.append({
                        "model": model.name,
                        "explore": explore.name,
                        "key": f"{model.name}.{explore.name}",
                        "label": explore.label or explore.name,
                        "description": explore.description or "",
                        "hidden": explore.hidden or False,
                    })

            progress.update(
                task,
                description=f"✓ Found {len(explores_list)} explores across {len(models)} models",
            )

    except Exception as e:
        console.print(f"[red]Error listing explores:[/red] {e}")
        raise

    return explores_list


def print_explores_list(explores: list[dict[str, Any]], show_hidden: bool = False) -> None:
    """
    Print list of explores in a readable format.

    Args:
        explores: List of explore dictionaries from list_all_explores
        show_hidden: Whether to show hidden explores
    """
    # Filter hidden if requested
    if not show_hidden:
        explores = [e for e in explores if not e.get("hidden")]

    # Group by model
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for explore in explores:
        by_model[explore["model"]].append(explore)

    console.print(
        f"\n[bold]Found {len(explores)} explore(s) across {len(by_model)} model(s)[/bold]\n"
    )

    # Print by model
    for model_name in sorted(by_model.keys()):
        model_explores = by_model[model_name]
        console.print(f"[bold cyan]{model_name}[/bold cyan] ({len(model_explores)} explores)")

        for explore in sorted(model_explores, key=lambda x: x["explore"]):
            hidden_marker = " [dim](hidden)[/dim]" if explore.get("hidden") else ""
            console.print(f"  • {explore['key']}{hidden_marker}")

            if explore.get("label") and explore["label"] != explore["explore"]:
                console.print(f"    Label: {explore['label']}")
            if explore.get("description"):
                # Truncate long descriptions
                desc = explore["description"]
                if len(desc) > 100:
                    desc = desc[:97] + "..."
                console.print(f"    {desc}")

        console.print()


def list_all_folders(client: LookerClient) -> list[dict[str, Any]]:
    """
    List all folders in the Looker instance.

    Returns list of folder dictionaries with id, name, and parent_id.
    """
    folders = client.sdk.all_folders()

    folder_data = []
    for folder in folders:
        folder_data.append({
            "id": folder.id,
            "name": folder.name,
            "parent_id": folder.parent_id,
        })

    return folder_data


def print_folders_list(folders: list[dict[str, Any]]) -> None:
    """Print folders list to console in a tree-like structure."""
    # Create parent-child mapping
    children_map: dict[str | None, list[dict[str, Any]]] = {}
    folders_by_id: dict[str, dict[str, Any]] = {}

    for folder in folders:
        folder_id = folder["id"]
        parent_id = folder["parent_id"]

        folders_by_id[folder_id] = folder

        if parent_id not in children_map:
            children_map[parent_id] = []
        children_map[parent_id].append(folder)

    def print_tree(folder_id: str | None, indent: int = 0) -> None:
        """Recursively print folder tree."""
        if folder_id not in children_map:
            return

        for folder in sorted(children_map[folder_id], key=lambda f: f["name"]):
            prefix = "  " * indent
            console.print(f"{prefix}• [cyan]{folder['id']}[/cyan]: {folder['name']}")
            print_tree(folder["id"], indent + 1)

    console.print(f"\n[bold]Found {len(folders)} folder(s):[/bold]\n")

    # Print root folders (parent_id = None)
    print_tree(None)

    console.print()


def get_folders_by_name(client: LookerClient, folder_name: str) -> list[dict[str, Any]]:
    """
    Find all folders matching a folder name.

    Args:
        client: Looker client instance
        folder_name: Folder name or identifier to search for

    Returns:
        List of folder dicts matching the folder name
    """
    all_folders = list_all_folders(client)

    # Filter folders where name ends with the folder name
    matching_folders = [folder for folder in all_folders if folder["name"].endswith(folder_name)]

    return matching_folders


def get_folder_inventory(client: LookerClient, folder_name: str) -> dict[str, Any]:
    """
    Get inventory of all content for folders matching a given name.

    Args:
        client: Looker client instance
        folder_name: Folder name or identifier to search for

    Returns:
        Dictionary with folder content inventory
    """
    # Find folders matching this name
    folders = get_folders_by_name(client, folder_name)

    if not folders:
        return {
            "folder_name": folder_name,
            "folders": [],
            "users": [],
            "dashboards": [],
            "looks": [],
            "total_content": 0,
            "error": f"No folders found matching '{folder_name}'",
        }

    # Extract unique user names from folder names
    users = set()
    for folder in folders:
        # Folder name format: "{User Name} {Folder Identifier}"
        name_parts = folder["name"].rsplit(" " + folder_name, 1)
        if len(name_parts) == 2:
            users.add(name_parts[0])

    # Get all dashboards (cached)
    all_dashboards = client.get_all_dashboards_cached(fields="id,title,folder")

    # Filter dashboards in matching folders
    folder_ids = {folder["id"] for folder in folders}
    folder_dashboards = []

    for dashboard in all_dashboards:
        if dashboard.folder and dashboard.folder.id in folder_ids:
            folder_dashboards.append({
                "id": dashboard.id,
                "title": dashboard.title or "Untitled",
                "folder_id": dashboard.folder.id,
            })

    # Get all looks (cached)
    all_looks = client.get_all_looks_cached(fields="id,title,folder")

    # Filter looks in matching folders
    folder_looks = []
    for look in all_looks:
        if look.folder and look.folder.id in folder_ids:
            folder_looks.append({
                "id": look.id,
                "title": look.title or "Untitled",
                "folder_id": look.folder.id,
            })

    return {
        "folder_name": folder_name,
        "folders": folders,
        "users": sorted(list(users)),
        "dashboards": folder_dashboards,
        "looks": folder_looks,
        "total_content": len(folder_dashboards) + len(folder_looks),
    }


def print_folder_inventory(inventory: dict[str, Any]) -> None:
    """Print folder inventory to console."""
    folder_name = inventory["folder_name"]

    if "error" in inventory:
        console.print(f"\n[yellow]{inventory['error']}[/yellow]\n")
        return

    console.print(f"\n[bold]Folder Inventory: {folder_name}[/bold]\n")

    # Users
    if inventory["users"]:
        console.print(f"[bold]Users ({len(inventory['users'])}):[/bold]")
        for user in inventory["users"][:20]:
            console.print(f"  • {user}")
        if len(inventory["users"]) > 20:
            console.print(f"  ... and {len(inventory['users']) - 20} more")
        console.print()

    # Folders
    console.print(f"[bold]Folders:[/bold] {len(inventory['folders'])}")
    console.print(f"[bold]Dashboards:[/bold] {len(inventory['dashboards'])}")
    console.print(f"[bold]Looks:[/bold] {len(inventory['looks'])}")
    console.print(f"[bold]Total Content:[/bold] {inventory['total_content']}\n")

    # Sample dashboards
    if inventory["dashboards"]:
        console.print("[bold]Sample Dashboards:[/bold]")
        for dashboard in inventory["dashboards"][:10]:
            console.print(f"  • [cyan]{dashboard['id']}[/cyan]: {dashboard['title']}")
        if len(inventory["dashboards"]) > 10:
            console.print(f"  ... and {len(inventory['dashboards']) - 10} more")
        console.print()


def get_folder_dependencies(client: LookerClient, folder_name: str) -> dict[str, Any]:
    """
    Analyze what explores and fields folders depend on.

    Args:
        client: Looker client instance
        folder_name: Folder name or identifier

    Returns:
        Dictionary with dependency analysis
    """
    # Get folder inventory first
    inventory = get_folder_inventory(client, folder_name)

    if "error" in inventory:
        return inventory

    # Get dashboard IDs
    dashboard_ids = [d["id"] for d in inventory["dashboards"]]

    if not dashboard_ids:
        return {
            "folder_name": folder_name,
            "usage_map": {},
            "explores_used": [],
            "total_explores": 0,
            "total_fields": 0,
            "note": "No dashboards found for these folders",
        }

    # Analyze dashboards using existing function
    analysis = analyze_specific_dashboards(client, dashboard_ids)

    # Transform usage_map to be more readable
    explores_used = []
    total_fields = 0

    for explore_key, fields in analysis["usage_map"].items():
        explores_used.append({
            "explore": explore_key,
            "fields": list(fields.keys()),
            "field_count": len(fields),
        })
        total_fields += len(fields)

    return {
        "folder_name": folder_name,
        "usage_map": analysis["usage_map"],
        "explores_used": explores_used,
        "total_explores": len(explores_used),
        "total_fields": total_fields,
        "dashboards_analyzed": analysis["stats"]["dashboards_analyzed"],
    }


def print_folder_dependencies(dependencies: dict[str, Any]) -> None:
    """Print folder dependencies to console."""
    folder_name = dependencies["folder_name"]

    if "error" in dependencies:
        console.print(f"\n[yellow]{dependencies['error']}[/yellow]\n")
        return

    if "note" in dependencies:
        console.print(f"\n[dim]{dependencies['note']}[/dim]\n")
        return

    console.print(f"\n[bold]Folder Dependencies: {folder_name}[/bold]\n")

    console.print(f"[bold]Dashboards Analyzed:[/bold] {dependencies['dashboards_analyzed']}")
    console.print(f"[bold]Explores Used:[/bold] {dependencies['total_explores']}")
    console.print(f"[bold]Unique Fields:[/bold] {dependencies['total_fields']}\n")

    if dependencies["explores_used"]:
        console.print("[bold]Explore Usage:[/bold]\n")

        # Sort by field count (most used first)
        sorted_explores = sorted(
            dependencies["explores_used"], key=lambda x: x["field_count"], reverse=True
        )

        for explore_info in sorted_explores[:10]:
            console.print(f"  • [cyan]{explore_info['explore']}[/cyan]")
            console.print(f"    Fields: {explore_info['field_count']}")

            # Show top fields
            for field in explore_info["fields"][:5]:
                console.print(f"      - {field}")
            if len(explore_info["fields"]) > 5:
                console.print(f"      ... and {len(explore_info['fields']) - 5} more")
            console.print()

        if len(sorted_explores) > 10:
            console.print(f"  ... and {len(sorted_explores) - 10} more explores\n")


def get_folder_performance(
    client: LookerClient, folder_name: str, slow_threshold_seconds: float = 5.0
) -> dict[str, Any]:
    """
    Analyze dashboard performance for folders matching a name.

    Args:
        client: LookerClient instance
        folder_name: Folder name to analyze
        slow_threshold_seconds: Threshold for slow queries (default: 5.0 seconds)

    Returns:
        Dict with performance metrics including slow dashboards
    """
    # Get matching folders
    folders = get_folders_by_name(client, folder_name)

    if not folders:
        return {
            "folder_name": folder_name,
            "error": f"No folders found matching: {folder_name}",
        }

    # Extract folder IDs
    folder_ids = [f["id"] for f in folders]

    # Get all dashboards
    all_dashboards = client.get_all_dashboards_cached(fields="id,title,folder,dashboard_elements")

    # Filter dashboards in these folders
    folder_dashboards = [
        d for d in all_dashboards if d.folder and d.folder.id and d.folder.id in folder_ids
    ]

    if not folder_dashboards:
        return {
            "folder_name": folder_name,
            "note": f"Folders matching '{folder_name}' have no dashboards.",
        }

    # Analyze performance for each dashboard
    slow_dashboards = []
    total_queries = 0
    total_slow_queries = 0

    for dashboard in folder_dashboards:
        # Get dashboard elements with queries
        if not dashboard.dashboard_elements:
            continue

        dashboard_slow_queries = []

        for element in dashboard.dashboard_elements:
            if not element.query:
                continue

            total_queries += 1

            # Run query and get performance metrics
            try:
                query = element.query
                if not query.id:
                    continue

                # Get query runtime from query results
                # Note: This is an estimate - real performance would require running the query
                # For now, we'll check if the query has runtime metadata
                query_details = client.sdk.query(query.id)

                # Check if query has runtime info (this is a simplified approach)
                # In production, you might want to run the query or check historical stats
                runtime = query_details.runtime if hasattr(query_details, "runtime") else None

                if (
                    runtime is not None
                    and isinstance(runtime, (int, float))
                    and runtime > slow_threshold_seconds
                ):
                    total_slow_queries += 1
                    dashboard_slow_queries.append({
                        "query_id": query.id,
                        "element_title": element.title or "Untitled",
                        "runtime_seconds": runtime,
                    })

            except Exception as e:
                # Skip queries that fail to analyze
                console.print(f"[dim]Warning: Could not analyze query: {e}[/dim]")
                continue

        if dashboard_slow_queries:
            slow_dashboards.append({
                "dashboard_id": dashboard.id,
                "title": dashboard.title or "Untitled Dashboard",
                "folder_name": dashboard.folder.name if dashboard.folder else "Unknown",
                "slow_queries": dashboard_slow_queries,
                "slow_query_count": len(dashboard_slow_queries),
                "avg_runtime": sum(q["runtime_seconds"] for q in dashboard_slow_queries)
                / len(dashboard_slow_queries),
            })

    # Sort by slow query count
    slow_dashboards.sort(key=lambda x: x["slow_query_count"], reverse=True)

    return {
        "folder_name": folder_name,
        "total_dashboards": len(folder_dashboards),
        "total_queries_analyzed": total_queries,
        "slow_threshold_seconds": slow_threshold_seconds,
        "dashboards_with_slow_queries": len(slow_dashboards),
        "total_slow_queries": total_slow_queries,
        "slow_dashboards": slow_dashboards,
        "folders_analyzed": len(folders),
    }


def print_folder_performance(performance: dict[str, Any]) -> None:
    """Print folder performance analysis to console."""
    folder_name = performance["folder_name"]

    if "error" in performance:
        console.print(f"\n[yellow]{performance['error']}[/yellow]\n")
        return

    if "note" in performance:
        console.print(f"\n[dim]{performance['note']}[/dim]\n")
        return

    console.print(f"\n[bold]Performance Analysis: {folder_name}[/bold]\n")

    console.print(f"[bold]Total Dashboards:[/bold] {performance['total_dashboards']}")
    console.print(f"[bold]Queries Analyzed:[/bold] {performance['total_queries_analyzed']}")
    console.print(f"[bold]Slow Threshold:[/bold] {performance['slow_threshold_seconds']}s")
    console.print(
        f"[bold]Dashboards with Slow Queries:[/bold] {performance['dashboards_with_slow_queries']}"
    )
    console.print(f"[bold]Total Slow Queries:[/bold] {performance['total_slow_queries']}\n")

    if performance["slow_dashboards"]:
        console.print("[bold]Slow Dashboards:[/bold]\n")

        for dashboard in performance["slow_dashboards"][:20]:
            console.print(f"  • [cyan]{dashboard['dashboard_id']}[/cyan]: {dashboard['title']}")
            console.print(f"    Folder: {dashboard['folder_name']}")
            console.print(f"    Slow Queries: {dashboard['slow_query_count']}")
            console.print(f"    Avg Runtime: {dashboard['avg_runtime']:.2f}s")

            # Show slow query details
            for query in dashboard["slow_queries"][:3]:
                console.print(f"      - {query['element_title']}: {query['runtime_seconds']:.2f}s")
            if len(dashboard["slow_queries"]) > 3:
                console.print(f"      ... and {len(dashboard['slow_queries']) - 3} more")
            console.print()

        if len(performance["slow_dashboards"]) > 20:
            console.print(f"  ... and {len(performance['slow_dashboards']) - 20} more dashboards\n")
    else:
        console.print("[green]✓ No slow dashboards found![/green]\n")
