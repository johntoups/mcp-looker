#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "shandy-sqlfmt[jinjafmt]==0.27.0",
# ]
# requires-python = ">=3.10,<3.13"
# ///
# vi: ft=python:
"""
Format SQL blocks in LookML files using sqlfmt.

This script finds SQL blocks between 'sql:' and ';;' markers in LookML files,
formats them using sqlfmt (with Jinja support), and preserves the original indentation.

Requirements:
  - uv installed (pip install uv)
  - Uses uvx to run sqlfmt with Jinja template support
"""

import argparse
import re
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Dict, Tuple

from sqlfmt.api import format_string
from sqlfmt.mode import Mode as Mode


def replace_looker_vars(sql: str) -> Tuple[str, Dict[str, str]]:
    """
    Replace LookML template variables ${...} with sentinel values.

    Args:
        sql: SQL string with LookML variables

    Returns:
        Tuple of (modified SQL, mapping of sentinels to original values)
    """
    # Pattern to match ${...} variables
    pattern = r"\$\{[^}]+\}"

    # Find all unique LookML variables
    variables = list(set(re.findall(pattern, sql)))

    # Create mapping
    mapping = {}
    modified_sql = sql

    for i, var in enumerate(variables):
        sentinel = f"__LOOKER_VAR_{i}__"
        mapping[sentinel] = var
        # Replace all occurrences of this variable with the same sentinel
        modified_sql = modified_sql.replace(var, sentinel)

    return modified_sql, mapping


def restore_looker_vars(sql: str, mapping: Dict[str, str]) -> str:
    """
    Restore LookML template variables from sentinel values.

    Args:
        sql: SQL string with sentinel values
        mapping: Dictionary mapping sentinels to original variables

    Returns:
        SQL string with restored LookML variables
    """
    restored_sql = sql

    # Sort by sentinel length (descending) to avoid partial replacements
    for sentinel, original in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
        # Handle case-insensitive replacement since sqlfmt might lowercase
        # First try exact match
        restored_sql = restored_sql.replace(sentinel, original)
        # Then try lowercase version
        restored_sql = restored_sql.replace(sentinel.lower(), original)

    return restored_sql


def format_sql_with_sqlfmt(sql: str) -> str:
    """
    Format SQL string using sqlfmt command line tool via uvx.
    Handles LookML template variables by temporarily replacing them.

    Args:
        sql: Raw SQL string to format

    Returns:
        Formatted SQL string with LookML variables preserved
    """
    # Replace LookML variables with sentinels
    modified_sql, mapping = replace_looker_vars(sql)

    try:
        # Use sqlfmt via uvx
        formatted = format_string(modified_sql, mode=Mode(single_process=True))

        # If sqlfmt returns empty (can happen with parse errors), return original
        if not formatted:
            return sql

        # Restore LookML variables
        formatted_with_vars = restore_looker_vars(formatted, mapping)
        return formatted_with_vars

    except Exception:
        # Silently return original SQL if formatting fails
        # This can still happen with complex Jinja templates
        return sql


def format_sql_block(match: re.Match) -> str:
    """
    Format a single SQL block match.

    Args:
        match: Regex match object containing the SQL block

    Returns:
        Formatted SQL block with proper indentation
    """
    # Extract components from the match
    leading_spaces = match.group(1)  # Indentation before 'sql:'
    sql_prefix = match.group(2)  # 'sql:' part (may include trailing spaces) # noqa: F841
    sql_content = match.group(3)  # The actual SQL content
    closing = match.group(4)  # The closing ';;' # noqa: F841

    # Strip the SQL content
    sql_content = sql_content.strip()

    # Check if it's a simple single-line SQL (like ${TABLE}.field)
    # Simple means: starts with ${, contains no operators except dot, and is relatively short
    is_simple_reference = (
        not sql_content  # Empty
        or (
            sql_content.startswith("${")
            and not any(
                op in sql_content
                for op in [
                    "+",
                    "-",
                    "*",
                    "/",
                    "=",
                    "<",
                    ">",
                    " AND ",
                    " OR ",
                    "CASE",
                    "WHEN",
                    "SELECT",
                    "FROM",
                ]
            )
            and len(sql_content) < 100
        )  # Reasonable length for a simple reference
    )

    if is_simple_reference:
        # Keep simple references on the same line
        return f"{leading_spaces}sql: {sql_content} ;;"

    # For complex SQL, format it
    formatted_sql = format_sql_with_sqlfmt(sql_content).strip()

    # Check if the formatted SQL is multi-line
    if "\n" in formatted_sql:
        # Multi-line SQL: put on new line and indent properly
        # The SQL should be indented 2 spaces more than the 'sql:' line
        sql_indent = leading_spaces + "  "
        indented_sql = textwrap.indent(formatted_sql, sql_indent)

        # Build the final block
        return f"{leading_spaces}sql:\n{indented_sql}\n{leading_spaces};;"
    else:
        # Single line SQL after formatting
        return f"{leading_spaces}sql: {formatted_sql} ;;"


def process_lookml_file(file_path: Path, dry_run: bool = False, backup: bool = True) -> bool:
    """
    Process a single LookML file to format SQL blocks.

    Args:
        file_path: Path to the LookML file
        dry_run: If True, only show what would be changed
        backup: If True, create a backup before modifying

    Returns:
        True if file was modified, False otherwise
    """
    try:
        content = file_path.read_text()
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        return False

    # Pattern to match SQL blocks
    # This handles both single-line and multi-line SQL blocks
    # Group 1: leading spaces
    # Group 2: 'sql:' with optional trailing spaces
    # Group 3: SQL content (everything between sql: and ;;)
    # Group 4: closing ';;'
    pattern = r"^(\s*)(sql:\s*)(.*?)(;;)"

    # Compile regex with MULTILINE and DOTALL flags
    regex = re.compile(pattern, re.MULTILINE | re.DOTALL)

    # Find and replace all SQL blocks
    new_content = regex.sub(format_sql_block, content)

    # Check if content changed
    if new_content == content:
        print(f"No changes needed in {file_path}")
        return False

    if dry_run:
        print(f"Would modify {file_path}")
        print("=" * 60)
        # Show a diff-like output for the first few changes
        import difflib

        diff = difflib.unified_diff(
            content.splitlines(keepends=True)[:50],
            new_content.splitlines(keepends=True)[:50],
            fromfile=str(file_path),
            tofile=str(file_path) + " (formatted)",
            n=3,
        )
        print("".join(diff))
        return True

    # Create backup if requested
    if backup:
        backup_path = file_path.with_suffix(file_path.suffix + ".bak")
        shutil.copy2(file_path, backup_path)
        print(f"Created backup: {backup_path}")

    # Write the formatted content
    file_path.write_text(new_content)
    print(f"Formatted {file_path}")
    return True


def find_lookml_files(path: Path, recursive: bool = False) -> list[Path]:
    """
    Find all LookML files in the given path.

    Args:
        path: Directory or file path
        recursive: If True, search recursively

    Returns:
        List of LookML file paths
    """
    if path.is_file():
        if path.suffix == ".lkml":
            return [path]
        else:
            print(f"Warning: {path} is not a .lkml file", file=sys.stderr)
            return []

    if path.is_dir():
        if recursive:
            return list(path.rglob("*.lkml"))
        else:
            return list(path.glob("*.lkml"))

    print(f"Error: {path} not found", file=sys.stderr)
    return []


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Format SQL blocks in LookML files using sqlfmt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Format a single file
  %(prog)s views/CE/gcp.view.lkml

  # Format all .lkml files in a directory
  %(prog)s views/CE/

  # Format recursively with dry run
  %(prog)s views/ --recursive --dry-run

  # Format without creating backups
  %(prog)s views/CE/gcp.view.lkml --no-backup
        """,
    )

    parser.add_argument(
        "path",
        type=Path,
        help="Path to a LookML file or directory containing LookML files",
    )

    parser.add_argument(
        "-r", "--recursive", action="store_true", help="Process directories recursively"
    )

    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying files",
    )

    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create backup files (*.lkml.bak)",
    )

    args = parser.parse_args()

    # Find all LookML files to process
    files = find_lookml_files(args.path, args.recursive)

    if not files:
        print("No LookML files found to process", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(files)} LookML file(s) to process")

    # Process each file
    modified_count = 0
    for file_path in files:
        if process_lookml_file(file_path, args.dry_run, not args.no_backup):
            modified_count += 1

    # Summary
    if args.dry_run:
        print(f"\nDry run complete. Would modify {modified_count}/{len(files)} file(s)")
    else:
        print(f"\nProcessing complete. Modified {modified_count}/{len(files)} file(s)")

    return 0 if modified_count > 0 or not files else 1


if __name__ == "__main__":
    sys.exit(main())
