# CLI Reference

Complete command reference for the Looker CLI.

## Command Groups

| Group | Purpose |
|-------|---------|
| [`session`](#session-commands) | Manage workspaces and git branches |
| [`export`](#export-commands) | Export and push LookML files |
| [`validate`](#validate-commands) | Validate LookML projects |
| [`analyze`](#analyze-commands) | Analyze usage and discover fields |
| [`deps`](#deps-commands) | Map dependencies and find issues |
| [`query-test`](#query-test-commands) | AB testing and golden tests |
| [`test`](#test-command) | Test API connection |

## Session Commands

Manage Looker workspaces and development branches.

### `session info`

Show current session information.

```bash
lookerctl session info
```

**Output**:
```
Current Session
  Workspace ID: dev
  User ID: 123
```

### `session list-projects`

List all Looker projects.

```bash
lookerctl session list-projects
```

**Output**:
```
Found 5 project(s):

  • my-project (ID: my_project)
    Git: git@github.com:org/my-project.git
    Production branch: master

  • analytics (ID: analytics_project)
    Git: git@github.com:org/analytics.git
    Production branch: main
```

###`session workspace <workspace_id>`

Switch to a different workspace.

**Arguments**:
- `workspace_id`: Either `dev` or `production`

```bash
# Switch to development workspace
lookerctl session workspace dev

# Switch to production workspace
lookerctl session workspace production
```

### `session checkout <project_id> <branch>`

Checkout a git branch in a Looker project.

**Arguments**:
- `project_id`: Project identifier
- `branch`: Git branch name

```bash
lookerctl session checkout my-project feature/new-dashboard
```

### `session sync [project_id]`

Sync Looker project with local git branch.

Automatically detects your current local git branch and checks out the corresponding branch in Looker.

**Arguments**:
- `project_id` (optional): Project to sync. If not provided, uses first available project.

```bash
# Sync first available project
lookerctl session sync

# Sync specific project
lookerctl session sync my-project
```

**How it works**:
1. Detects your current local git branch (`git branch --show-current`)
2. Switches Looker to dev workspace
3. Checks out matching branch in Looker
4. Resets to remote to pull latest commits
5. Shows synced commit SHA

**Output example**:
```
Local git branch: perf/optimize-lookml-2
✓ Checked out branch 'perf/optimize-lookml-2'
Pulling latest commits from remote...
✓ Reset to remote completed
✓ Synced to commit: ce6fd70
```

**Note**: This ensures Looker gets the latest commits from the remote, not just the branch name. No need for manual `reset_project_to_remote()` calls.

### `session create-branch <project_id> <branch_name> [--from <source_branch>]`

Create a new development branch in a Looker project.

**Arguments**:
- `project_id`: Project identifier
- `branch_name`: Name for new branch

**Options**:
- `--from <branch>`: Branch to create from (defaults to production branch)

```bash
# Create from production branch
lookerctl session create-branch my-project feature/new-feature

# Create from specific branch
lookerctl session create-branch my-project hotfix/bug-123 \
  --from develop
```

### `session git-status [project_id]`

Show git status for a Looker project.

**Arguments**:
- `project_id` (optional): Project to check. If not provided, uses first available project.

```bash
lookerctl session git-status my-project
```

**Output**:
```
Git Status for My Project

  Project ID: my-project
  Remote URL: git@github.com:org/my-project.git
  Current branch: feature/new-feature
  Production branch: master

  ✓ Currently on development branch
```

## Export Commands

Export and push LookML content.

### `export project [project_id] [-o <dir>] [-b <branch>]`

Export LookML files from a single project.

**Arguments**:
- `project_id` (optional): Project to export. If not provided, uses first available project.

**Options**:
- `-o, --output-dir <dir>`: Output directory (default: `./looker_export`)
- `-b, --branch <branch>`: Git branch to export from

```bash
# Export first available project
lookerctl export project

# Export specific project
lookerctl export project my-project -o ./local

# Export from specific branch
lookerctl export project my-project -b develop
```

**Output**:
```
✓ Exported 145 files (12.45 MB) to ./local
```

### `export all [-o <dir>]`

Export LookML files from all projects.

**Options**:
- `-o, --output-dir <dir>`: Base directory for exports (default: `./looker_export`)

```bash
lookerctl export all -o ./all-lookml
```

**Output**:
```
Export Summary:
  Projects: 5
  Total files: 523
  Total size: 48.32 MB
```

### `export sync [project_id] [-b <branch>]`

Sync a project from its git repository.

**Arguments**:
- `project_id` (optional): Project to sync

**Options**:
- `-b, --branch <branch>`: Git branch to sync to

```bash
lookerctl export sync my-project
```

### `export push <project_id> <local_dir> [--no-validate]`

Push local LookML files to Looker dev branch.

**Arguments**:
- `project_id`: Project identifier
- `local_dir`: Path to local LookML directory

**Options**:
- `--no-validate`: Skip validation after push

```bash
# Push and validate
lookerctl export push my-project ./local

# Push without validation
lookerctl export push my-project ./local --no-validate
```

**How it works**:
1. Switches to dev workspace automatically
2. Pushes all .lkml files to Looker
3. Validates the project (unless `--no-validate`)
4. Shows validation errors with file paths and line numbers

**Output**:
```
✓ Pushed 145 file(s) to project my-project

Validation Results:
  ✓ No errors found
```

## Validate Commands

Validate LookML projects for errors.

### `validate project [project_id]`

Validate a project in Looker.

**Arguments**:
- `project_id` (optional): Project to validate

```bash
lookerctl validate project my-project
```

**Output**:
```
Validating project: my-project

✗ Found 3 error(s):

  [ERROR] Field 'total_amount' not found in view 'users'
    File: views/orders.view.lkml
    Line: 45

  [ERROR] View 'user_facts' not found
    File: views/users.view.lkml
    Line: 78

  [ERROR] Joined view 'inventory' not found in explore 'orders'
    File: explores/sales.explore.lkml
    Line: 12
```

### `validate local <project_id> <local_dir>`

Validate local LookML files by pushing to Looker dev branch.

**Arguments**:
- `project_id`: Project identifier
- `local_dir`: Path to local LookML directory

```bash
lookerctl validate local my-project ./local
```

**How it works**:
1. Pushes local files to Looker dev branch
2. Runs Looker's validation engine
3. Returns validation errors
4. **Same validation as Looker console**

**Use case**: Get Looker console validation on local changes before committing.

**Time**: ~40 seconds (includes push + validation)

### `validate static <project_dir> [--view <view>] [--explore <explore>] [-o <file>]`

Fast local LookML validation without API calls.

**Arguments**:
- `project_dir`: Path to LookML project directory

**Options**:
- `--view <view>`: Validate specific view only
- `--explore <explore>`: Validate specific explore only
- `-o, --output <file>`: Output errors to JSON file

```bash
# Validate entire project
lookerctl validate static ./local

# Validate specific view
lookerctl validate static ./local --view users

# Validate specific explore
lookerctl validate static ./local --explore user_orders

# Export errors to JSON
lookerctl validate static ./local -o errors.json
```

**How it works**:
1. Parses all .lkml files into in-memory graph
2. Validates field references, view existence, explore structure
3. No API calls, no git sync, works offline

**Time**: ~600ms (66x faster than API validation!)

**Output**:
```
Parsing LookML project: ./local

✓ Loaded 145 views, 42 explores, 3 models

Validating all views and explores...

Found 2 validation error(s):

  views/orders.view.lkml:45 - Field 'total_amount' not found in view 'users'
  views/users.view.lkml:78 - View 'user_facts' not found
```

**See**: [Local Validation Guide](./LOCAL_VALIDATION.md) for details.

## Analyze Commands

Analyze usage and discover fields.

### `analyze usage [-o <file>]`

Analyze explore and field usage across dashboards and looks.

**Options**:
- `-o, --output <file>`: Export analysis to JSON file

```bash
# Show usage summary
lookerctl analyze usage

# Export to JSON
lookerctl analyze usage -o usage.json
```

**Output**:
```
Usage Analysis

Analyzed:
  Dashboards: 234
  Looks: 156

Found:
  Explores: 78
  Total field references: 1,523

Top Explores by Usage:
  1. sales.user_orders (145 fields)
  2. analytics.daily_metrics (98 fields)
  3. product.inventory (67 fields)
```

**JSON output** (`usage.json`):
```json
{
  "usage_map": {
    "sales.user_orders": {
      "users.id": ["Dashboard: Sales Overview", "Look: User Analysis"],
      "orders.total_revenue": ["Dashboard: Revenue Tracking"]
    }
  },
  "explore_field_counts": {
    "sales.user_orders": 145
  }
}
```

### `analyze unused`

Find explores not used in any dashboards or looks.

```bash
lookerctl analyze unused
```

**Output**:
```
Finding unused explores...

Found 12 unused explore(s):

  • legacy.old_orders
  • test.experimental_feature
  • deprecated.user_metrics
  ... and 9 more
```

### `analyze explore <explore_name> [-m <model>]`

Analyze usage of a specific explore.

**Arguments**:
- `explore_name`: Explore name or `model.explore` format

**Options**:
- `-m, --model <model>`: Model name (if not in explore_name)

```bash
# Using model.explore notation
lookerctl analyze explore sales.user_orders

# Using --model flag
lookerctl analyze explore user_orders --model sales
```

**Output**:
```
Analyzing explore: sales.user_orders

Found 23 field(s) in use:

users.id
  Used in 5 location(s):
    • Dashboard: Sales Overview
    • Dashboard: User Analysis
    • Look: Top Users
    ... and 2 more

orders.total_revenue
  Used in 3 location(s):
    • Dashboard: Revenue Tracking
    • Look: Monthly Revenue
    ... and 1 more
```

### `analyze explore-fields <explore_name> [-m <model>] [-o <file>] [--show-hidden]`

Discover all available fields in an explore (API method).

**Arguments**:
- `explore_name`: Explore name or `model.explore` format

**Options**:
- `-m, --model <model>`: Model name
- `-o, --output <file>`: Export to JSON file
- `--show-hidden`: Show hidden fields

```bash
lookerctl analyze explore-fields sales.user_orders -o fields.json
```

**How it works**:
- Queries Looker API for actual runtime schema
- Shows what fields are really available to query
- Includes fields from joined views

**Time**: ~2 seconds

**Output** (`fields.json`):
```json
{
  "explore": "user_orders",
  "fields": {
    "dimensions": [
      {
        "name": "users.id",
        "type": "number",
        "description": "User ID",
        "sql": "${TABLE}.id",
        "hidden": false
      }
    ],
    "measures": [
      {
        "name": "orders.total_revenue",
        "type": "sum",
        "description": "Total revenue",
        "sql": "${TABLE}.total",
        "hidden": false
      }
    ]
  }
}
```

**Critical for**: Generating query specifications for baselines and tests.

### `analyze explore-fields-local <project_dir> <explore_name> [-o <file>] [--show-hidden]`

Discover explore fields locally without API calls (instant).

**Arguments**:
- `project_dir`: Path to LookML project
- `explore_name`: Explore name

**Options**:
- `-o, --output <file>`: Export to JSON file
- `--show-hidden`: Show hidden fields

```bash
lookerctl analyze explore-fields-local ./local user_orders -o fields.json
```

**How it works**:
- Parses local LookML files
- Resolves view inheritance and joins
- Applies field scoping rules

**Time**: ~100ms (20x faster than API!)

**Use when**: Rapid iteration during development, offline work.

### `analyze list-explores [-o <file>] [--show-hidden]`

List all available model.explore combinations.

**Options**:
- `-o, --output <file>`: Export to JSON file
- `--show-hidden`: Show hidden explores

```bash
# List all explores
lookerctl analyze list-explores

# Export to JSON
lookerctl analyze list-explores -o explores.json

# Search for specific explore
lookerctl analyze list-explores | grep -i "orders"
```

**Output**:
```
Discovering all explores...

Found 1,052 explore(s) across 228 model(s)

QA0_CF (3 explores)
  • QA0_CF.feature_activations
    Label: Feature Flag Activations
  • QA0_CF.feature_flags_v2
    Label: Feature Flags
  • QA0_CF.targets_v2
    Label: Targets

sales (15 explores)
  • sales.user_orders
    Label: User Orders
  • sales.revenue_analysis
    Label: Revenue Analysis
```

**Use when**: Discovering correct model.explore names for testing.

## Deps Commands

Analyze and visualize dependencies.

### `deps build [project_dir] [-o <file>] [-f <format>]`

Build dependency graph for a LookML project.

**Arguments**:
- `project_dir` (optional): Project directory (defaults to current directory)

**Options**:
- `-o, --output <file>`: Output file for graph
- `-f, --format <format>`: Output format (`json` or `dot`, default: `json`)

```bash
# Build graph for current directory
lookerctl deps build

# Build for specific directory
lookerctl deps build ./lookml -o graph.json

# Export as GraphViz DOT format
lookerctl deps build ./lookml -o graph.dot -f dot
```

**Output**:
```
Dependency Graph Statistics:

  Total nodes: 187
  Total edges: 342
  Views: 145
  Explores: 42
  Avg dependencies per node: 1.83
  Avg dependents per node: 1.83
```

### `deps tree <node_name> [project_dir] [-d <depth>]`

Show dependency tree for a view or explore.

**Arguments**:
- `node_name`: View or explore name
- `project_dir` (optional): Project directory

**Options**:
- `-d, --depth <depth>`: Maximum depth to traverse (default: 5)

```bash
lookerctl deps tree users ./lookml --depth 3
```

**Output**:
```
Dependency tree for: users

users
├── base_user (extends)
├── user_facts (references ${users.id})
└── order_facts
    └── orders (references ${order_facts.user_id})
```

### `deps impact <node_name> [project_dir]`

Analyze the impact of changing/removing a view or explore.

**Arguments**:
- `node_name`: View or explore name
- `project_dir` (optional): Project directory

```bash
lookerctl deps impact users ./lookml
```

**Output**:
```
Impact Analysis: users

Direct dependents: 3
  • user_orders (extends users)
  • user_facts (references ${users.id})
  • customer_360 (joins users)

Transitive dependents: 8
  • All views affected by changes to users

Explores affected: 5
  • sales.user_orders
  • analytics.user_cohorts
  • product.user_preferences
  ... and 2 more
```

### `deps orphaned [project_dir]`

Find views that are not used by any explores.

**Arguments**:
- `project_dir` (optional): Project directory

```bash
lookerctl deps orphaned ./lookml
```

**Output**:
```
Found 7 orphaned view(s):

  • legacy_user_temp
  • old_orders_backup
  • test_view_123
  ... and 4 more
```

### `deps cycles [project_dir]`

Find circular dependencies in the LookML project.

**Arguments**:
- `project_dir` (optional): Project directory

```bash
lookerctl deps cycles ./lookml
```

**Output**:
```
Found 2 circular dependenc(ies):

  1. users → user_facts → users
  2. orders → order_items → orders
```

## Query-Test Commands

Query testing, baselines, and golden tests.

### Baseline Commands

#### `query-test baseline create <explore> -q <file> [-o <file>] [--dry-run]`

Create a baseline by running a query and capturing results.

**Arguments**:
- `explore`: Explore in `model.explore` format

**Options**:
- `-q, --query-file <file>`: JSON file with query specification (required)
- `-o, --output <file>`: Output file for baseline
- `--dry-run`: Validate query without creating baseline

```bash
# Dry run - test query
lookerctl query-test baseline create sales.user_orders \
  -q query.json --dry-run

# Create baseline
lookerctl query-test baseline create sales.user_orders \
  -q query.json -o baseline.json
```

**Query file format** (`query.json`):
```json
{
  "fields": ["users.count", "orders.total_revenue"],
  "filters": {"users.state": "California"},
  "sorts": ["orders.total_revenue desc"],
  "limit": "100"
}
```

**Baseline output** (`baseline.json`):
```json
{
  "explore": "sales.user_orders",
  "query": { /* query spec */ },
  "results": [ /* actual data */ ],
  "row_count": 100,
  "performance": {
    "runtime_seconds": 2.34,
    "status": "complete"
  },
  "metadata": {
    "created_at": "2025-01-15T10:00:00Z",
    "git_branch": "main"
  }
}
```

#### `query-test baseline compare <explore> -b <file> [--tolerance <float>] [-o <file>]`

Run query and compare results to baseline.

**Arguments**:
- `explore`: Explore in `model.explore` format

**Options**:
- `-b, --baseline <file>`: Baseline file to compare against (required)
- `--tolerance <float>`: Numeric tolerance for comparisons (default: 0.01)
- `-o, --output <file>`: Output file for comparison results

```bash
lookerctl query-test baseline compare sales.user_orders \
  -b baseline.json \
  --tolerance 0.01
```

**Output**:
```
┏━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Metric      ┃ Baseline ┃ Current ┃ Change           ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ Row Count   │ 100      │ 100     │ ✓ +0             │
│ Runtime (s) │ 2.34     │ 1.89    │ ✓ -0.45s (-19.2%)│
└─────────────┴──────────┴─────────┴──────────────────┘

✓ Comparison PASSED
```

**Exit codes**:
- `0`: Comparison passed (data identical)
- `1`: Comparison failed (data differs)

### Golden Test Commands

#### `query-test golden create <explore> -n <name> -q <file> -e <file> [--scope <scope>] [-d <dir>]`

Create a golden test with expected results.

**Arguments**:
- `explore`: Explore in `model.explore` format

**Options**:
- `-n, --name <name>`: Test name (required)
- `-q, --query-file <file>`: Query specification (required)
- `-e, --expected-file <file>`: Expected results (required)
- `--scope <scope>`: Test scope (`permanent` or `feature_branch`, default: `permanent`)
- `-d, --test-dir <dir>`: Directory to store tests (default: `./golden_tests`)

```bash
lookerctl query-test golden create sales.user_orders \
  --name "revenue_test" \
  -q query.json \
  -e expected.json \
  --scope permanent
```

**Expected file format** (`expected.json`):
```json
{
  "row_count": 100,
  "schema": {
    "users.count": "number",
    "orders.total_revenue": "number"
  },
  "data": [
    /* optional - actual data to validate */
  ]
}
```

#### `query-test golden run [--name <name>] [-d <dir>] [-o <file>]`

Run golden tests.

**Options**:
- `--name <name>`: Run specific test by name
- `-d, --test-dir <dir>`: Directory containing tests (default: `./golden_tests`)
- `-o, --output <file>`: Output file for results

```bash
# Run all tests
lookerctl query-test golden run

# Run specific test
lookerctl query-test golden run --name revenue_test

# Save results
lookerctl query-test golden run -o results.json
```

**Output**:
```
Running 3 golden test(s)

  Test: revenue_test
  Rows: 100
  Runtime: 1.2s
  Status: ✓ PASSED

  Test: user_metrics
  Rows: 50
  Runtime: 0.8s
  Status: ✓ PASSED

  Test: order_summary
  Rows: 25
  Runtime: 2.1s
  Status: ✗ FAILED
  Failures:
    • Row 5, field users.count: expected 150, got 148

Summary
  Total: 3
  Passed: 2
  Failed: 1
```

#### `query-test golden list [-d <dir>]`

List all golden tests.

**Options**:
- `-d, --test-dir <dir>`: Directory containing tests

```bash
lookerctl query-test golden list
```

**Output**:
```
Golden Tests (3)

  • revenue_test
    Explore: sales.user_orders
    Scope: permanent
    Created: 2025-01-15T10:00:00Z

  • user_metrics
    Explore: analytics.user_cohorts
    Scope: permanent
    Created: 2025-01-14T15:30:00Z
```

#### `query-test golden delete -n <name> [-d <dir>]`

Delete a golden test.

**Options**:
- `-n, --name <name>`: Test name to delete (required)
- `-d, --test-dir <dir>`: Directory containing tests

```bash
lookerctl query-test golden delete --name revenue_test
```

## Test Command

### `test`

Test Looker API connection and authentication.

```bash
lookerctl test
```

**Output**:
```
Configuration:
  Base URL: https://your-instance.looker.com:443
  API Version: 4.0
  Client ID: abc123...
  Verify SSL: true

Testing connection...

✓ Session workspace: dev
✓ Found 47 project(s)
    • project_1
    • project_2
    ... and 45 more
✓ Found 422 LookML model(s)
    • model_1
    • model_2
    ... and 420 more

✓ All tests passed!
```

**Use when**:
- First time setup
- Verifying credentials
- Debugging connection issues
- Checking API access

---

## Global Options

All commands support:

```bash
--help    # Show command help
--version # Show CLI version
```

## Exit Codes

- `0`: Success
- `1`: Error or validation failed
- `2`: Command usage error

## Environment Variables

Required:
```bash
LOOKERSDK_BASE_URL          # Looker instance URL
LOOKERSDK_CLIENT_ID         # API client ID
LOOKERSDK_CLIENT_SECRET     # API client secret
```

Optional:
```bash
LOOKERSDK_API_VERSION       # API version (default: 4.0)
LOOKERSDK_VERIFY_SSL        # Verify SSL (default: true)
LOOKERSDK_TIMEOUT           # Request timeout (default: 120)
```

## Next Steps

- **[Workflows](./WORKFLOWS.md)** - Common command patterns
- **[Examples](./EXAMPLES.md)** - Real-world usage examples
- **[Query Testing](./QUERY_TESTING.md)** - Deep dive on testing
- **[Local Validation](./LOCAL_VALIDATION.md)** - Deep dive on local graph

---

**Tip**: Use `lookerctl <command> --help` to see help for any command.
