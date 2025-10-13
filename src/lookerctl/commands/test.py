"""Query testing, baseline comparison, and golden test management."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import git
from looker_sdk import models40 as models
from rich.console import Console
from rich.table import Table

from lookerctl.core.client import LookerClient
from lookerctl.utils.git import get_current_branch

console = Console()


def get_rendered_sql(
    client: LookerClient,
    model: str,
    explore: str,
    fields: list[str],
    filters: Optional[dict[str, str]] = None,
    sorts: Optional[list[str]] = None,
    limit: int = 500,
) -> dict[str, Any]:
    """
    Get the SQL that Looker would generate without executing the query.

    Uses run_inline_query with result_format="sql" to get rendered SQL.

    Args:
        client: Looker client instance
        model: Model name
        explore: Explore name
        fields: List of field names
        filters: Optional filters dict
        sorts: Optional sorts list
        limit: Row limit (default: 500)

    Returns:
        Dictionary with:
        - sql: The rendered SQL query
        - model: Model name
        - explore: Explore name
        - query: Query specification that was rendered
    """
    try:
        # Use run_inline_query with result_format="sql"
        sql_result = client.sdk.run_inline_query(
            result_format="sql",
            body=models.WriteQuery(
                model=model,
                view=explore,
                fields=fields,
                filters=filters or {},
                sorts=sorts or [],
                limit=str(limit),
            ),
        )

        return {
            "sql": sql_result,
            "model": model,
            "explore": explore,
            "query": {
                "fields": fields,
                "filters": filters or {},
                "sorts": sorts or [],
                "limit": str(limit),
            },
        }

    except Exception as e:
        error_msg = str(e)
        console.print(f"[red]Error getting SQL:[/red] {error_msg}")

        # Provide helpful error messages
        if "View Not Found" in error_msg or "404" in error_msg:
            console.print("\n[yellow]Troubleshooting:[/yellow]")
            console.print("  • The model.explore combination may be incorrect")
            console.print("  • List all available explores:")
            console.print("    [cyan]./looker.py analyze list-explores[/cyan]")

        raise


def run_query_and_capture(
    client: LookerClient,
    model: str,
    explore: str,
    query_spec: dict[str, Any],
) -> dict[str, Any]:
    """
    Run a query against an explore and capture results + performance.

    Args:
        client: Looker client instance
        model: Model name
        explore: Explore name
        query_spec: Query specification (fields, filters, sorts, limit, etc.)

    Returns:
        Dictionary with results, performance metrics, and metadata
    """
    try:
        # Create query
        start_time = time.time()

        # Create query using models40 (proven to work)
        query = client.sdk.create_query(
            body=models.WriteQuery(
                model=model,
                view=explore,
                fields=query_spec.get("fields", []),
                filters=query_spec.get("filters", {}),
                sorts=query_spec.get("sorts", []),
                limit=query_spec.get("limit", "500"),
                vis_config=query_spec.get("vis_config"),
            )
        )

        # Run query
        console.print(f"Running query on {model}.{explore}...")

        if not query.id:
            raise ValueError("Query creation failed - no query ID returned")

        result = client.sdk.run_query(
            query_id=query.id,
            result_format="json",
        )

        end_time = time.time()
        runtime = end_time - start_time

        # Parse results
        results = json.loads(result) if isinstance(result, str) else result

        # Get query performance info (may not be available for all queries)
        query_status = "complete"
        try:
            query_task = client.sdk.query_task(query.id)
            if query_task and query_task.status:
                query_status = query_task.status
        except Exception:
            # Query task info not available, assume complete since we got results
            pass

        return {
            "explore": f"{model}.{explore}",
            "query": {
                "fields": query_spec.get("fields", []),
                "filters": query_spec.get("filters", {}),
                "sorts": query_spec.get("sorts", []),
                "limit": query_spec.get("limit", "500"),
            },
            "results": results,
            "row_count": len(results) if isinstance(results, list) else 0,
            "performance": {
                "runtime_seconds": runtime,
                "status": query_status,
            },
            "metadata": {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "query_id": query.id,
            },
        }

    except Exception as e:
        error_msg = str(e)
        console.print(f"[red]Error running query:[/red] {error_msg}")

        # Provide helpful error messages for common issues
        if "View Not Found" in error_msg or "404" in error_msg:
            console.print("\n[yellow]Troubleshooting:[/yellow]")
            console.print("  • The model.explore combination may be incorrect")
            console.print("  • List all available explores:")
            console.print("    [cyan]./looker.py analyze list-explores[/cyan]")
            console.print("  • Or search for a specific explore:")
            console.print(f"    [cyan]./looker.py analyze list-explores | grep -i {explore}[/cyan]")
            console.print("  • Verify you have access to this explore")
            console.print()

        raise


def create_baseline(
    client: LookerClient,
    model: str,
    explore: str,
    query_spec: dict[str, Any],
    output_file: Path,
    include_git_info: bool = True,
) -> dict[str, Any]:
    """
    Create a baseline by running a query and saving results.

    Args:
        client: Looker client instance
        model: Model name
        explore: Explore name
        query_spec: Query specification
        output_file: Where to save baseline
        include_git_info: Whether to include git commit info

    Returns:
        Baseline data
    """
    console.print(f"\n[bold]Creating baseline for {model}.{explore}[/bold]\n")

    # Run query and capture results
    baseline = run_query_and_capture(client, model, explore, query_spec)

    # Add git info if requested
    if include_git_info:
        try:
            repo = git.Repo(search_parent_directories=True)
            baseline["metadata"]["git_branch"] = get_current_branch()
            baseline["metadata"]["git_commit"] = repo.head.commit.hexsha
        except Exception:
            pass

    # Save to file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(baseline, indent=2))

    console.print(f"[green]✓[/green] Baseline created: {output_file}")
    console.print(f"  Rows: {baseline['row_count']}")
    console.print(f"  Runtime: {baseline['performance']['runtime_seconds']:.2f}s\n")

    return baseline


def compare_to_baseline(
    client: LookerClient,
    model: str,
    explore: str,
    baseline_file: Path,
    tolerance: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Run query and compare results to baseline.

    Args:
        client: Looker client instance
        model: Model name
        explore: Explore name
        baseline_file: Path to baseline file
        tolerance: Comparison tolerances (numeric_tolerance, etc.)

    Returns:
        Comparison results
    """
    console.print(f"\n[bold]Comparing to baseline: {baseline_file}[/bold]\n")

    # Load baseline
    baseline = json.loads(baseline_file.read_text())

    # Run current query
    current = run_query_and_capture(client, model, explore, baseline["query"])

    # Compare results
    comparison = {
        "baseline": {
            "row_count": baseline["row_count"],
            "runtime": baseline["performance"]["runtime_seconds"],
        },
        "current": {
            "row_count": current["row_count"],
            "runtime": current["performance"]["runtime_seconds"],
        },
        "differences": {
            "row_count_changed": current["row_count"] != baseline["row_count"],
            "data_changed": False,
            "data_differences": [],
        },
        "performance": {
            "runtime_delta": current["performance"]["runtime_seconds"]
            - baseline["performance"]["runtime_seconds"],
            "runtime_percent_change": (
                (
                    (
                        current["performance"]["runtime_seconds"]
                        - baseline["performance"]["runtime_seconds"]
                    )
                    / baseline["performance"]["runtime_seconds"]
                )
                * 100
                if baseline["performance"]["runtime_seconds"] > 0
                else 0
            ),
        },
        "passed": True,
    }

    # Compare data
    if baseline["row_count"] == current["row_count"]:
        numeric_tolerance = (tolerance or {}).get("numeric_tolerance", 0.01)

        for i, (baseline_row, current_row) in enumerate(
            zip(baseline["results"], current["results"])
        ):
            row_diffs = []
            for key in baseline_row.keys():
                baseline_val = baseline_row.get(key)
                current_val = current_row.get(key)

                # Compare values with tolerance for numbers
                if isinstance(baseline_val, (int, float)) and isinstance(current_val, (int, float)):
                    if abs(baseline_val - current_val) > numeric_tolerance:
                        row_diffs.append({
                            "field": key,
                            "baseline": baseline_val,
                            "current": current_val,
                            "delta": current_val - baseline_val,
                        })
                elif baseline_val != current_val:
                    row_diffs.append({
                        "field": key,
                        "baseline": baseline_val,
                        "current": current_val,
                    })

            if row_diffs:
                comparison["differences"]["data_changed"] = True
                comparison["differences"]["data_differences"].append({
                    "row": i,
                    "differences": row_diffs,
                })

    # Determine if comparison passed
    if comparison["differences"]["row_count_changed"]:
        comparison["passed"] = False
    if comparison["differences"]["data_changed"]:
        comparison["passed"] = False

    return comparison


def print_comparison_results(comparison: dict[str, Any]) -> None:
    """Print comparison results in a readable format."""
    console.print("\n[bold]Comparison Results[/bold]\n")

    # Summary table
    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Baseline")
    table.add_column("Current")
    table.add_column("Change")

    # Row count
    baseline_rows = comparison["baseline"]["row_count"]
    current_rows = comparison["current"]["row_count"]
    row_delta = current_rows - baseline_rows
    row_status = "✓" if row_delta == 0 else "✗"

    table.add_row(
        "Row Count",
        str(baseline_rows),
        str(current_rows),
        f"{row_status} {row_delta:+d}",
    )

    # Runtime
    baseline_runtime = comparison["baseline"]["runtime"]
    current_runtime = comparison["current"]["runtime"]
    runtime_delta = comparison["performance"]["runtime_delta"]
    runtime_pct = comparison["performance"]["runtime_percent_change"]

    runtime_status = "✓" if runtime_delta <= 0 else "⚠"
    table.add_row(
        "Runtime (s)",
        f"{baseline_runtime:.2f}",
        f"{current_runtime:.2f}",
        f"{runtime_status} {runtime_delta:+.2f}s ({runtime_pct:+.1f}%)",
    )

    console.print(table)

    # Data differences
    if comparison["differences"]["data_changed"]:
        console.print("\n[yellow]Data Differences Found:[/yellow]")
        console.print(
            f"  {len(comparison['differences']['data_differences'])} row(s) with differences\n"
        )

        for diff in comparison["differences"]["data_differences"][:5]:
            console.print(f"  Row {diff['row']}:")
            for field_diff in diff["differences"]:
                console.print(f"    {field_diff['field']}:")
                console.print(f"      Baseline: {field_diff['baseline']}")
                console.print(f"      Current:  {field_diff['current']}")
                if "delta" in field_diff:
                    console.print(f"      Delta:    {field_diff['delta']:+.2f}")

        if len(comparison["differences"]["data_differences"]) > 5:
            remaining = len(comparison["differences"]["data_differences"]) - 5
            console.print(f"\n  ... and {remaining} more row(s) with differences")

    # Overall status
    if comparison["passed"]:
        console.print("\n[green bold]✓ Comparison PASSED[/green bold]\n")
    else:
        console.print("\n[red bold]✗ Comparison FAILED[/red bold]\n")


def create_golden_test(
    name: str,
    model: str,
    explore: str,
    query_spec: dict[str, Any],
    expected: dict[str, Any],
    test_dir: Path,
    scope: str = "permanent",
    tolerance: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Create a golden test with expected results.

    Args:
        name: Test name
        model: Model name
        explore: Explore name
        query_spec: Query specification
        expected: Expected results (row_count, data, schema)
        test_dir: Directory to store tests
        scope: 'permanent' or 'feature_branch'
        tolerance: Comparison tolerances

    Returns:
        Golden test definition
    """
    test = {
        "name": name,
        "explore": f"{model}.{explore}",
        "query": query_spec,
        "expected": expected,
        "tolerance": tolerance
        or {
            "numeric_tolerance": 0.01,
            "allow_extra_rows": False,
            "allow_missing_rows": False,
        },
        "metadata": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "scope": scope,
        },
    }

    # Save test
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / f"{name}.json"
    test_file.write_text(json.dumps(test, indent=2))

    console.print(f"[green]✓[/green] Created golden test: {name}")
    console.print(f"  Saved to: {test_file}\n")

    return test


def run_golden_test(client: LookerClient, test_file: Path) -> dict[str, Any]:
    """
    Run a golden test and validate results.

    Args:
        client: Looker client instance
        test_file: Path to test definition

    Returns:
        Test results
    """
    # Load test
    test = json.loads(test_file.read_text())

    console.print(f"\n[bold]Running golden test: {test['name']}[/bold]")

    # Parse explore
    model, explore = test["explore"].split(".", 1)

    # Run query
    current = run_query_and_capture(client, model, explore, test["query"])

    # Validate results
    result = {
        "test_name": test["name"],
        "passed": True,
        "failures": [],
        "current_row_count": current["row_count"],
        "expected_row_count": test["expected"].get("row_count"),
        "runtime": current["performance"]["runtime_seconds"],
    }

    # Check row count
    if "row_count" in test["expected"]:
        expected_count = test["expected"]["row_count"]
        if current["row_count"] != expected_count:
            if (
                not test["tolerance"].get("allow_extra_rows")
                and current["row_count"] > expected_count
            ):
                result["passed"] = False
                result["failures"].append(
                    f"Too many rows: expected {expected_count}, got {current['row_count']}"
                )
            elif (
                not test["tolerance"].get("allow_missing_rows")
                and current["row_count"] < expected_count
            ):
                result["passed"] = False
                result["failures"].append(
                    f"Too few rows: expected {expected_count}, got {current['row_count']}"
                )

    # Check schema
    if "schema" in test["expected"] and current["results"]:
        expected_schema = test["expected"]["schema"]
        actual_row = current["results"][0]

        for field, expected_type in expected_schema.items():
            if field not in actual_row:
                result["passed"] = False
                result["failures"].append(f"Missing field: {field}")

    # Check data if provided
    if "data" in test["expected"] and test["expected"]["data"] is not None:
        expected_data = test["expected"]["data"]
        numeric_tolerance = test["tolerance"].get("numeric_tolerance", 0.01)

        for i, expected_row in enumerate(expected_data):
            if i >= len(current["results"]):
                result["passed"] = False
                result["failures"].append(f"Missing row at index {i}")
                continue

            current_row = current["results"][i]

            for key, expected_val in expected_row.items():
                current_val = current_row.get(key)

                # Compare with tolerance for numbers
                if isinstance(expected_val, (int, float)) and isinstance(current_val, (int, float)):
                    if abs(expected_val - current_val) > numeric_tolerance:
                        result["passed"] = False
                        result["failures"].append(
                            f"Row {i}, field {key}: expected {expected_val}, got {current_val}"
                        )
                elif expected_val != current_val:
                    result["passed"] = False
                    result["failures"].append(
                        f"Row {i}, field {key}: expected {expected_val}, got {current_val}"
                    )

    return result


def print_test_result(result: dict[str, Any]) -> None:
    """Print golden test result."""
    console.print(f"\n  Test: [cyan]{result['test_name']}[/cyan]")
    console.print(f"  Rows: {result['current_row_count']}")
    console.print(f"  Runtime: {result['runtime']:.2f}s")

    if result["passed"]:
        console.print("  Status: [green]✓ PASSED[/green]\n")
    else:
        console.print("  Status: [red]✗ FAILED[/red]")
        console.print("  Failures:")
        for failure in result["failures"][:5]:
            console.print(f"    • {failure}")
        if len(result["failures"]) > 5:
            console.print(f"    ... and {len(result['failures']) - 5} more\n")


def run_all_golden_tests(client: LookerClient, test_dir: Path) -> dict[str, Any]:
    """
    Run all golden tests in a directory.

    Args:
        client: Looker client instance
        test_dir: Directory containing test files

    Returns:
        Summary of all test results
    """
    test_files = list(test_dir.glob("*.json"))

    if not test_files:
        console.print(f"[yellow]No tests found in {test_dir}[/yellow]")
        return {"total": 0, "passed": 0, "failed": 0, "results": []}

    console.print(f"\n[bold]Running {len(test_files)} golden test(s)[/bold]\n")

    results = []
    for test_file in test_files:
        try:
            result = run_golden_test(client, test_file)
            results.append(result)
            print_test_result(result)
        except Exception as e:
            console.print(f"[red]Error running test {test_file.name}:[/red] {e}\n")
            results.append({
                "test_name": test_file.stem,
                "passed": False,
                "failures": [str(e)],
            })

    # Summary
    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed

    summary = {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
    }

    console.print("[bold]Summary[/bold]")
    console.print(f"  Total: {summary['total']}")
    console.print(f"  Passed: [green]{summary['passed']}[/green]")
    console.print(f"  Failed: [red]{summary['failed']}[/red]\n")

    return summary
