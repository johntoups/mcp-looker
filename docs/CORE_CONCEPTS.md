# Core Concepts

Understanding these concepts will help you use the Looker CLI effectively.

## The Core Problem

Your Looker instance is **embedded in your product**. Customers create:
- Custom dashboards
- Custom explores
- Custom LookML content

You face these challenges:

❌ **No visibility** - Can't see what customers created
❌ **No usage data** - Don't know which fields are actually used
❌ **No safe optimization** - Risk breaking customer dashboards
❌ **No local development** - Must work in Looker UI
❌ **No AI workflows** - Tools can't access or modify LookML

## The Solution: Complete Local Development Loop

This CLI provides a **Looker console-like experience** that's:
- **Local** - Work on your filesystem
- **Fast** - 66x faster validation than API
- **Safe** - AB testing before changes go live
- **AI-ready** - All data in JSON format
- **Scientific** - Measure impact objectively

## Key Concepts

### 1. Export → Local → Push Loop

**Traditional Looker Development:**
```
Edit in UI → Validate in UI → Commit in UI → Deploy
```
- Can't automate
- No AI access
- Slow iteration

**CLI Development:**
```
Export → Edit Locally → Validate Locally → Push → Commit
```
- Fully automated
- AI accessible
- Rapid iteration

**Example**:
```bash
# Get LookML locally
lookerctl export project my-project -o ./local

# Edit files (AI or human)
vim ./local/views/users.view.lkml

# Validate locally (600ms!)
lookerctl validate static ./local

# Push back to Looker
lookerctl export push my-project ./local
```

### 2. Two Validation Modes

#### API Validation (Accurate, Slow)

```bash
lookerctl validate local my-project ./local
```

- **Speed**: 40+ seconds
- **Accuracy**: 100% (uses Looker's engine)
- **Requires**: API connection, git sync
- **Use when**: Final validation before merge

**How it works**:
1. Pushes local files to Looker dev branch
2. Runs Looker's validation engine
3. Returns errors with file/line numbers

#### Local Graph Validation (Fast, Good)

```bash
lookerctl validate static ./local
```

- **Speed**: 600ms (66x faster!)
- **Accuracy**: ~95% (parses LookML locally)
- **Requires**: Nothing - works offline
- **Use when**: Rapid iteration during development

**How it works**:
1. Parses all .lkml files into in-memory graph
2. Validates field references, view existence
3. Checks dependency structure
4. No API calls needed

**Recommendation**: Use static during development, API validation before commit.

### 3. Usage Analysis

**The Problem**: You don't know which fields customers actually use.

**The Solution**: Scan all dashboards and looks to build usage map.

```bash
lookerctl analyze usage -o usage.json
```

**Output** (`usage.json`):
```json
{
  "usage_map": {
    "sales.user_orders": {
      "users.id": ["Dashboard: Sales Overview", "Look: User Analysis"],
      "users.name": ["Dashboard: Sales Overview"],
      "orders.total_revenue": ["Dashboard: Revenue Tracking"]
    }
  },
  "explore_field_counts": {
    "sales.user_orders": 45
  }
}
```

**AI Usage**: AI reads `usage.json` to understand:
- Which fields are safe to change
- Which fields are never used (can be hidden/removed)
- Which explores are most critical
- Where fields are referenced

### 4. Dependency Mapping

**The Problem**: You don't know what breaks when you change a view.

**The Solution**: Build complete dependency graph.

```bash
lookerctl deps build ./lookml -o deps.json
```

**Generates**:
- View → View dependencies (extends, refinements)
- Explore → View dependencies (joins)
- Transitive impact analysis

**Example**:
```bash
# Show what depends on 'users' view
lookerctl deps impact users

# Output:
# Direct dependents: 3 views
# - user_orders (extends users)
# - user_facts (references ${users.id})
# - customer_360 (joins users)
#
# Explores affected: 5
# - sales.user_orders
# - analytics.user_cohorts
# ... and 3 more
```

**AI Usage**: Before changing a view, AI:
1. Runs `deps impact view_name`
2. Identifies all affected explores
3. Creates baselines for each affected explore
4. Makes changes
5. Compares to baselines
6. Ensures nothing broke

### 5. Scientific Testing: Baselines & AB Tests

**The Problem**: You optimize LookML but don't know if it actually helped.

**The Solution**: Capture state before/after and compare scientifically.

#### Baseline

A snapshot of query results and performance:

```json
{
  "explore": "sales.user_orders",
  "query": { /* query spec */ },
  "results": [ /* actual data */ ],
  "row_count": 500,
  "performance": {
    "runtime_seconds": 3.45,
    "status": "complete"
  },
  "metadata": {
    "created_at": "2025-01-15T10:00:00Z",
    "git_branch": "main",
    "git_commit": "abc123"
  }
}
```

#### AB Test

Compare before/after:

```bash
# BEFORE changes
lookerctl query-test baseline create model.explore \
  -q query.json -o before.json

# Make LookML changes
# ... optimize SQL, add indexes, refactor joins ...

# AFTER changes
lookerctl query-test baseline compare model.explore \
  -b before.json
```

**Output**:
```
Metric      | Baseline | Current | Change
------------|----------|---------|------------------
Row Count   | 500      | 500     | ✓ +0
Runtime (s) | 3.45     | 2.10    | ✓ -1.35s (-39.1%)

✓ Comparison PASSED
Performance improved by 39.1% with no data changes!
```

**The test passes if**:
- ✅ Same row count
- ✅ Same data values (within tolerance)
- ⚡ Performance change measured (can be better/worse/same)

**AI Usage**: AI can now:
- Make optimization
- Measure actual impact
- Verify correctness
- Iterate until goals met

### 6. Golden Tests: Regression Prevention

**The Problem**: Optimizations today might break things tomorrow.

**The Solution**: Permanent tests with expected results.

```bash
# Create golden test
lookerctl query-test golden create model.explore \
  --name "revenue_test" \
  -q query.json \
  -e expected.json \
  --scope permanent

# Run all golden tests (in CI/CD)
lookerctl query-test golden run
```

**Golden tests check**:
- Row count matches expected
- Schema matches expected
- Data matches expected (optional)

**Use cases**:
- **Permanent**: Core business metrics, production explores
- **Feature branch**: Temporary validation during development

### 7. The LookML Runtime Graph

**What it is**: In-memory representation of entire LookML project.

**Built from**:
- All .lkml files parsed using `lkml` library
- View inheritance resolved (extends chains)
- Join relationships mapped
- Field references extracted

**Enables**:
- ⚡ 66x faster validation
- 🔍 Instant field discovery
- 🌐 Dependency analysis
- ✅ Offline validation

**How it works**:
```python
from lookerctl.utils.lookml_project import LookMLProject

# Parse entire project (600ms)
project = LookMLProject(Path("./lookml"))

# Now you have instant access to:
errors = project.validate_all()              # Validate everything
fields = project.get_explore_fields("orders")  # Get available fields
deps = project.get_dependencies("users")     # Get dependencies
```

**See**: [Local Validation Guide](./LOCAL_VALIDATION.md) for details.

### 8. Field Discovery

**The Problem**: To create a query, you need to know what fields exist.

**The Solution**: Discover available fields in an explore.

```bash
# Using API (accurate, includes calculated fields)
lookerctl analyze explore-fields sales.user_orders \
  -o fields.json

# Using local graph (fast, offline)
lookerctl analyze explore-fields-local ./lookml user_orders \
  -o fields.json
```

**Output** (`fields.json`):
```json
{
  "explore": "user_orders",
  "fields": {
    "dimensions": [
      {"name": "users.id", "type": "number", "description": "User ID"},
      {"name": "users.name", "type": "string", "description": "Full name"},
      {"name": "orders.status", "type": "string", "description": "Order status"}
    ],
    "measures": [
      {"name": "users.count", "type": "number", "description": "Count of users"},
      {"name": "orders.total_revenue", "type": "sum", "description": "Total revenue"}
    ]
  }
}
```

**AI Usage**: AI reads `fields.json` to:
- Discover what fields exist
- Understand field types
- Read field descriptions
- Generate valid query specifications

**Critical for**:
- Creating baseline queries
- Generating test queries
- Automated query creation
- Documentation generation

## How These Concepts Work Together

### AI Optimization Workflow

```
1. Export
   lookerctl export all -o ./lookml
   → AI has all LookML locally

2. Analyze Usage
   lookerctl analyze usage -o usage.json
   → AI knows what's actually used

3. Analyze Dependencies
   lookerctl deps build ./lookml -o deps.json
   → AI knows impact of changes

4. Discover Fields
   lookerctl analyze explore-fields sales.orders -o fields.json
   → AI knows available fields for queries

5. Create Baseline
   lookerctl query-test baseline create sales.orders -q query.json -o before.json
   → Capture current state

6. Make Changes
   AI edits .lkml files based on usage and dependency analysis

7. Validate Locally
   lookerctl validate static ./lookml
   → 600ms validation, iterate rapidly

8. Compare to Baseline
   lookerctl query-test baseline compare sales.orders -b before.json
   → Verify correctness and performance

9. Push Changes
   lookerctl export push my-project ./lookml
   → Deploy to Looker

10. Create Golden Test
    lookerctl query-test golden create sales.orders --name "orders_perf" ...
    → Prevent regressions
```

### Human Developer Workflow

```
1. Sync Branch
   lookerctl session sync my-project
   → Looker matches local git branch

2. Export
   lookerctl export project my-project -o ./local
   → Get current state

3. Make Changes
   vim ./local/views/users.view.lkml
   → Edit LookML

4. Validate (Fast!)
   lookerctl validate static ./local
   → Check for errors instantly

5. Push
   lookerctl export push my-project ./local
   → Deploy to dev branch

6. Commit
   git add . && git commit -m "Updated users view"
   → Save to version control
```

## Key Design Decisions

### Why JSON Everywhere?

**Decision**: All analysis outputs are JSON files.

**Reason**:
- Machine-readable (AI can consume)
- Structured data (easy to query)
- Composable (pipe between commands)
- Versionable (track changes in git)

### Why Two Validation Modes?

**Decision**: Both API and local graph validation.

**Reason**:
- **Local**: Speed for iteration (66x faster)
- **API**: Accuracy for final check (100% correct)
- Different use cases need different tradeoffs

### Why Baseline Comparison?

**Decision**: Capture state before/after, not just performance.

**Reason**:
- Correctness matters more than performance
- Data changes are breaking changes
- Performance is bonus, not requirement
- Scientific approach builds confidence

### Why Golden Tests?

**Decision**: Permanent tests with expected results.

**Reason**:
- Prevent regressions over time
- Document expected behavior
- Enable CI/CD integration
- Catch breaking changes early

## Data Flow

```
Looker Instance
      ↓ export
Local .lkml Files ← AI edits
      ↓ parse
LookML Graph
      ↓ analyze
  Usage Map, Dependency Graph, Field Lists (all JSON)
      ↓ consume
AI Decision Making
      ↓ generate
LookML Changes
      ↓ validate
Local Graph (600ms)
      ↓ test
Baseline Comparison
      ↓ push
Looker Dev Branch
      ↓ validate (final)
API Validation (40s)
      ↓ commit
Git Repository
```

## Mental Model

Think of the CLI as providing **three layers**:

1. **Export/Push Layer** - Get LookML in/out of Looker
2. **Analysis Layer** - Understand usage, dependencies, fields
3. **Testing Layer** - Validate correctness and performance

Each layer builds on the previous:
- Can't analyze without exporting first
- Can't test without knowing available fields
- Can't optimize without understanding usage

## Common Patterns

### Pattern: Safe Refactoring

```bash
# 1. Understand impact
lookerctl deps impact my_view

# 2. For each affected explore, create baseline
lookerctl query-test baseline create model.explore1 -q q1.json -o b1.json
lookerctl query-test baseline create model.explore2 -q q2.json -o b2.json

# 3. Make changes
vim ./local/views/my_view.view.lkml

# 4. Validate syntax
lookerctl validate static ./local

# 5. Compare to baselines
lookerctl query-test baseline compare model.explore1 -b b1.json
lookerctl query-test baseline compare model.explore2 -b b2.json

# 6. If all pass, push
lookerctl export push my-project ./local
```

### Pattern: AI Exploration

```bash
# 1. Export for analysis
lookerctl export all -o ./lookml

# 2. Generate analysis files
lookerctl analyze usage -o usage.json
lookerctl deps build ./lookml -o deps.json
lookerctl analyze list-explores -o explores.json

# 3. AI reads JSON files and discovers:
# - Which explores exist
# - Which fields are used where
# - How views depend on each other
# - What's safe to change

# 4. AI makes informed decisions
# - Hide unused fields
# - Remove orphaned views
# - Optimize frequently-used explores
# - Add missing indexes
```

### Pattern: Performance Optimization

```bash
# 1. Find slow explore from monitoring
# 2. Discover fields
lookerctl analyze explore-fields model.slow_explore -o fields.json

# 3. Create representative query
# (AI generates query.json from fields.json)

# 4. Baseline current performance
lookerctl query-test baseline create model.slow_explore \
  -q query.json -o baseline.json

# 5. Optimize
# - Persistent derived tables
# - Indexes
# - Join refactoring

# 6. Compare
lookerctl query-test baseline compare model.slow_explore -b baseline.json

# 7. Iterate until target met
# If performance improved 30% AND data correct → success!
```

## Summary

The key insight: **Treat LookML as data**.

- Export it to local files
- Parse it into structured graphs
- Analyze it programmatically
- Test it scientifically
- Deploy it safely

This enables:
- **Visibility** - See everything customers created
- **Safety** - Test before deploying
- **Speed** - Iterate rapidly (66x faster)
- **Automation** - AI can optimize
- **Confidence** - Measure actual impact

## Next Steps

Now that you understand the concepts:

1. **[CLI Reference](./CLI_REFERENCE.md)** - Complete command reference
2. **[Workflows](./WORKFLOWS.md)** - Common patterns and workflows
3. **[Query Testing](./QUERY_TESTING.md)** - Deep dive on baselines
4. **[Local Validation](./LOCAL_VALIDATION.md)** - Deep dive on LookML graph
5. **[AI Integration](./AI_INTEGRATION.md)** - AI-specific patterns

---

**Remember**: The CLI gives you a Looker console experience locally, with the speed and automation of command-line tools.
