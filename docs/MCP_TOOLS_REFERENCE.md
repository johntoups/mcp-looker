# MCP Tools Quick Reference

This is a quick reference for all MCP tools available in the Looker CLI MCP server.

## Best Practices

### ✅ Use MCP Tools (Not Inline Python)

**DON'T** create inline Python scripts for SDK calls:
```python
# ❌ BAD - Manual SDK usage
python3 << 'EOF'
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from lookerctl.core.client import LookerClient

with LookerClient() as client:
    query = client.sdk.create_query(...)
    sql = client.sdk.run_query(query.id, "sql")
EOF
```

**DO** use MCP tools instead:
```python
# ✅ GOOD - Use MCP tools
result = mcp__birdwatcher__get_query_sql(
    model="hub",
    explore="users",
    fields=["users.count"],
    filters={"users.created_date": "7 days"},
    limit=100
)
```

**Why MCP tools are better**:
1. **Less code**: No client setup, error handling, or serialization boilerplate
2. **Consistency**: Same code path for CLI and AI agents
3. **Caching**: MCP server manages API cache automatically
4. **Debugging**: Easier to trace issues using official tools
5. **Maintainability**: One implementation to maintain

### Query Testing Workflow

| Tool | When to Use | Example |
|------|-------------|---------|
| `get_query_sql` | Verify SQL generation without executing | Parameter substitution, SQL validation |
| `run_query` | Execute query and get results | Field availability testing, data validation |
| `create_query_baseline` | Capture results before changes | Before refactoring LookML |
| `compare_query_baseline` | Compare after changes | A/B testing after refactoring |

## Export Tools

### `export_project`
Export LookML files from a specific project.
```python
{
  "project_id": str,           # Required: Project ID to export
  "output_dir": str,           # Optional: Output directory (default: ./looker_export)
  "git_branch": str | None     # Optional: Git branch to export from
}
```

### `export_all_projects`
Export LookML files from all projects.
```python
{
  "output_dir": str            # Optional: Base directory (default: ./looker_export)
}
```

### `export_dashboards`
Export all user-defined dashboards as LookML.
```python
{
  "output_dir": str,           # Optional: Output directory (default: ./looker_export/dashboards)
  "limit": int | None          # Optional: Limit number of dashboards
}
```

### `export_looks`
Export all looks (saved queries) as JSON.
```python
{
  "output_dir": str,           # Optional: Output directory (default: ./looker_export/looks)
  "limit": int | None          # Optional: Limit number of looks
}
```

## Analysis Tools

### `analyze_usage`
Analyze explore and field usage across all dashboards and looks.
```python
{}  # No parameters
```
Returns: `usage_map`, `dashboard_stats`, `look_stats`, `total_explores`

### `find_unused_content`
Find explores not used in any dashboards or looks.
```python
{}  # No parameters
```
Returns: `unused_explores`, `total_unused`, `total_explores`

### `get_explore_schema`
Get complete schema for an explore including all fields.
```python
{
  "model": str,                # Required: Model name
  "explore": str               # Required: Explore name
}
```
Returns: Explore metadata, fields by type (dimensions, measures, filters, parameters)

### `list_explores`
List all available model.explore combinations.
```python
{}  # No parameters
```
Returns: `explores` (list), `total_explores` (count)

### `analyze_dependencies`
Build and analyze dependency graph for a LookML project.
```python
{
  "project_dir": str,          # Required: Path to LookML project directory
  "include_fields": bool       # Optional: Include field-level deps (default: False)
}
```
Returns: Dependency graph statistics

### `analyze_change_impact`
Analyze impact of changing/removing a view, explore, or field.
```python
{
  "project_dir": str,          # Required: Path to LookML project directory
  "node_name": str,            # Required: Node to analyze (e.g., "view.my_view")
  "include_fields": bool       # Optional: Include field-level impact (default: False)
}
```
Returns: Impact analysis with affected nodes

## Session/Workspace Tools

### `get_workspace`
Get current Looker workspace.
```python
{}  # No parameters
```
Returns: `workspace_id` ("dev" or "production")

### `set_workspace`
Switch to a different workspace.
```python
{
  "workspace_id": str          # Required: "dev" or "production"
}
```
Returns: `success`, `message`

### `get_git_status`
Get git status for a Looker project.
```python
{
  "project_id": str            # Required: Project ID
}
```
Returns: Project git info (branch, remote_url, etc.)

### `checkout_branch`
Checkout a git branch in a Looker project.
```python
{
  "project_id": str,           # Required: Project ID
  "branch": str                # Required: Branch name
}
```
Returns: `success`, `message`

### `create_branch`
Create a new development branch.
```python
{
  "project_id": str,           # Required: Project ID
  "branch_name": str,          # Required: New branch name
  "from_branch": str | None    # Optional: Branch to create from
}
```
Returns: `success`, `message`

## Project Tools

### `list_projects`
List all Looker projects.
```python
{}  # No parameters
```
Returns: `projects` (list with id, name, git info), `total_projects`

### `validate_project`
Validate a LookML project in Looker.
```python
{
  "project_id": str            # Required: Project ID
}
```
Returns: `has_errors`, `errors` (list of validation errors)

## Query Testing Tools

### `get_query_sql`
Get the SQL that Looker would generate without executing the query.
```python
{
  "model": str,                # Required: Model name
  "explore": str,              # Required: Explore name
  "fields": list[str],         # Required: List of field names
  "filters": dict | None,      # Optional: Filter dictionary
  "sorts": list[str] | None,   # Optional: Sort specifications
  "limit": int                 # Optional: Row limit (default: 500)
}
```
Returns: `sql` (string), `model`, `explore`, `query` (spec)

**Example**:
```python
result = mcp__birdwatcher__get_query_sql(
    model="hub",
    explore="users",
    fields=["users.count", "users.state"],
    filters={"users.created_date": "30 days"},
    limit=1000
)

# Verify parameter substitution
assert "'environment'" in result["sql"]
```

### `run_query`
Run a query against an explore and capture results.
```python
{
  "model": str,                # Required: Model name
  "explore": str,              # Required: Explore name
  "fields": list[str],         # Required: List of field names
  "filters": dict | None,      # Optional: Filter dictionary
  "sorts": list[str] | None,   # Optional: Sort specifications
  "limit": int                 # Optional: Row limit (default: 500)
}
```
Returns: Query results, `row_count`, performance metrics

### `create_query_baseline`
Create a baseline by running a query and saving results for A/B testing.
```python
{
  "model": str,                # Required: Model name
  "explore": str,              # Required: Explore name
  "fields": list[str],         # Required: List of field names
  "output_file": str,          # Required: Path to save baseline
  "filters": dict | None,      # Optional: Filter dictionary
  "sorts": list[str] | None,   # Optional: Sort specifications
  "limit": int                 # Optional: Row limit (default: 500)
}
```
Returns: Complete query results and metadata (saved to file)

### `compare_query_baseline`
Compare current query results to a saved baseline.
```python
{
  "model": str,                # Required: Model name
  "explore": str,              # Required: Explore name
  "baseline_file": str,        # Required: Path to baseline file
  "numeric_tolerance": float   # Optional: Tolerance for numeric diffs (default: 0.01)
}
```
Returns: `passed` (bool), `differences`, `summary`

## Dependency Analysis Tools

### `find_orphaned_views`
Find views not used by any explores.
```python
{
  "project_dir": str           # Required: Path to LookML project directory
}
```
Returns: `orphaned_views`, `total_orphaned`

### `find_circular_deps`
Find circular dependencies in a LookML project.
```python
{
  "project_dir": str           # Required: Path to LookML project directory
}
```
Returns: `circular_dependencies`, `total_cycles`

## Common Return Types

### Export Results
```python
{
  "files_exported": int,
  "total_size": int,
  "errors": list[str]
}
```

### Usage Analysis
```python
{
  "usage_map": dict,           # explore_key -> field -> locations
  "dashboard_stats": dict,
  "look_stats": dict,
  "total_explores": int
}
```

### Validation Results
```python
{
  "has_errors": bool,
  "errors": list[{
    "message": str,
    "file_path": str,
    "line_number": int,
    "severity": str
  }]
}
```

### Dependency Stats
```python
{
  "total_nodes": int,
  "total_edges": int,
  "total_views": int,
  "total_explores": int,
  "avg_dependencies": float,
  "avg_dependents": float
}
```

## Usage Examples

### With Claude Desktop

Ask Claude questions like:
- "List all projects in my Looker instance"
- "Export the analytics project to ./exports"
- "Find unused explores and show me the results"
- "Get the schema for model.users_explore"
- "What would be impacted if I change view.orders in ./lookml?"
- "Analyze dependencies in my local LookML project at ./lookml"

### Programmatic Usage

```python
from lookerctl.mcp_server import mcp

# Get tool by name
tool = mcp._tool_manager.get_tool("list_projects")

# Call tool (would be done by MCP client)
# result = tool.fn()
```

## Notes

- All tools handle LookerClient initialization automatically
- Environment variables must be set (LOOKERSDK_BASE_URL, etc.)
- Results are automatically serialized to JSON-compatible format
- Path parameters accept both absolute and relative paths
- Most tools return dictionaries with structured data
