# AI Integration Guide

How AI systems should use the Looker CLI for automated LookML optimization.

## Why This CLI is AI-Ready

**Traditional Looker**: Web UI only, no programmatic access to validation or testing.

**This CLI**: Every operation outputs JSON, all commands scriptable, complete automation possible.

Key AI benefits:
- **Visibility** - Export all LookML to analyze
- **Understanding** - Usage maps and dependency graphs in JSON
- **Validation** - Local graph validation in 600ms
- **Testing** - Scientific AB tests for correctness
- **Iteration** - Rapid edit→validate→test loops

## Core AI Workflow Pattern

```python
# 1. GATHER INTELLIGENCE
export_all_lookml()
analyze_usage() → usage.json
build_dependency_graph() → deps.json
list_all_explores() → explores.json

# 2. IDENTIFY OPPORTUNITIES
parse(usage.json, deps.json)
identify_optimizations()

# 3. PLAN CHANGES
for each optimization:
    analyze_impact()
    create_baseline()

# 4. EXECUTE CHANGES
for each optimization:
    modify_lookml_files()
    validate_locally()
    compare_to_baseline()
    if passed:
        push_to_looker()
        create_golden_test()
    else:
        revert_and_retry()

# 5. DOCUMENT
commit_to_git()
create_pr_with_metrics()
```

## JSON Data Formats for AI Consumption

### 1. Usage Map (`usage.json`)

```json
{
  "usage_map": {
    "sales.user_orders": {
      "users.id": [
        "Dashboard: Sales Overview (Tile 3)",
        "Dashboard: User Analysis (Tile 1)",
        "Look: Top Users by Revenue"
      ],
      "users.name": [
        "Dashboard: Sales Overview (Tile 3)"
      ],
      "orders.total_revenue": [
        "Dashboard: Revenue Tracking (Tile 1)",
        "Dashboard: Revenue Tracking (Tile 5)",
        "Look: Monthly Revenue Trends"
      ]
    },
    "analytics.user_cohorts": {
      "users.cohort_id": ["Dashboard: Cohort Analysis"],
      "users.signup_date": ["Dashboard: Cohort Analysis"]
    }
  },
  "explore_field_counts": {
    "sales.user_orders": 23,
    "analytics.user_cohorts": 45
  },
  "total_dashboards_analyzed": 234,
  "total_looks_analyzed": 156,
  "total_explores_found": 78
}
```

**AI uses this to**:
- Identify which fields are actually used
- Find unused fields (can be hidden/removed)
- Understand explore criticality (more usage = more critical)
- Know where fields are referenced (impact analysis)

### 2. Dependency Graph (`deps.json`)

```json
{
  "nodes": [
    {
      "id": "users",
      "type": "view",
      "file_path": "views/users.view.lkml"
    },
    {
      "id": "user_orders",
      "type": "explore",
      "model": "sales"
    }
  ],
  "edges": [
    {
      "source": "user_orders",
      "target": "users",
      "type": "joins",
      "metadata": {"join_type": "left_outer"}
    },
    {
      "source": "user_facts",
      "target": "users",
      "type": "references",
      "metadata": {"field": "${users.id}"}
    }
  ],
  "statistics": {
    "total_nodes": 187,
    "total_edges": 342,
    "total_views": 145,
    "total_explores": 42
  }
}
```

**AI uses this to**:
- Understand what depends on what
- Calculate blast radius of changes
- Find orphaned views (no dependents)
- Detect circular dependencies
- Plan safe refactoring order

### 3. Explore List (`explores.json`)

```json
{
  "total_explores": 1052,
  "explores": [
    {
      "model": "sales",
      "name": "user_orders",
      "label": "User Orders",
      "view_name": "orders",
      "hidden": false,
      "key": "sales.user_orders"
    },
    {
      "model": "analytics",
      "name": "user_cohorts",
      "label": "User Cohort Analysis",
      "view_name": "users",
      "hidden": false,
      "key": "analytics.user_cohorts"
    }
  ],
  "generated_at": "2025-10-11T18:00:00Z"
}
```

**AI uses this to**:
- Discover all available explores
- Get correct model.explore format for queries
- Filter hidden vs visible explores
- Map model→explores relationships

### 4. Field Discovery (`fields.json`)

```json
{
  "explore": "user_orders",
  "fields": {
    "dimensions": [
      {
        "name": "users.id",
        "type": "number",
        "description": "Unique user identifier",
        "sql": "${TABLE}.id",
        "hidden": false,
        "view": "users"
      },
      {
        "name": "users.email",
        "type": "string",
        "description": "User email address",
        "sql": "${TABLE}.email",
        "hidden": false,
        "view": "users"
      },
      {
        "name": "orders.created_at",
        "type": "timestamp",
        "description": "Order creation timestamp",
        "sql": "${TABLE}.created_at",
        "hidden": false,
        "view": "orders"
      }
    ],
    "measures": [
      {
        "name": "users.count",
        "type": "count",
        "description": "Count of unique users",
        "sql": "${TABLE}.id",
        "hidden": false,
        "view": "users"
      },
      {
        "name": "orders.total_revenue",
        "type": "sum",
        "description": "Total revenue from orders",
        "sql": "${TABLE}.amount",
        "hidden": false,
        "view": "orders"
      }
    ],
    "filters": [],
    "parameters": []
  },
  "field_counts": {
    "dimensions": 45,
    "measures": 23,
    "filters": 5,
    "parameters": 2,
    "total": 75
  }
}
```

**AI uses this to**:
- Discover available fields for query generation
- Understand field types and descriptions
- Generate valid query specifications
- Create baselines and tests

### 5. Baseline (`baseline.json`)

```json
{
  "explore": "sales.user_orders",
  "query": {
    "fields": ["users.count", "orders.total_revenue"],
    "filters": {"orders.created_year": "2024"},
    "sorts": ["orders.total_revenue desc"],
    "limit": "100"
  },
  "results": [
    {"users.count": 150, "orders.total_revenue": 50000},
    {"users.count": 120, "orders.total_revenue": 45000}
  ],
  "row_count": 100,
  "performance": {
    "runtime_seconds": 3.45,
    "status": "complete",
    "cache_hit": false
  },
  "metadata": {
    "created_at": "2025-01-15T10:00:00Z",
    "git_branch": "main",
    "git_commit": "abc123"
  }
}
```

**AI uses this to**:
- Capture state before optimizations
- Compare after optimizations
- Verify data correctness
- Measure performance improvements

## AI Implementation Examples

### Example 1: Python - Complete Optimization Pipeline

```python
#!/usr/bin/env python3
"""
AI-driven LookML optimization pipeline
"""

import subprocess
import json
from pathlib import Path

class LookerOptimizer:
    def __init__(self, project_id: str, lookml_dir: Path):
        self.project_id = project_id
        self.lookml_dir = lookml_dir

    def run_command(self, cmd: list[str]) -> dict:
        """Run CLI command and return JSON output"""
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        # Parse JSON output if available
        try:
            return json.loads(result.stdout)
        except:
            return {"stdout": result.stdout}

    def gather_intelligence(self):
        """Step 1: Export and analyze everything"""
        print("[1/5] Gathering intelligence...")

        # Export all LookML
        subprocess.run([
            "lookerctl", "export", "all",
            "-o", str(self.lookml_dir)
        ])

        # Analyze usage
        usage = self.run_command([
            "lookerctl", "analyze", "usage",
            "-o", "usage.json"
        ])

        # Build dependency graph
        deps = self.run_command([
            "lookerctl", "deps", "build", str(self.lookml_dir),
            "-o", "deps.json"
        ])

        # List explores
        explores = self.run_command([
            "lookerctl", "analyze", "list-explores",
            "-o", "explores.json"
        ])

        return {
            "usage": json.load(open("usage.json")),
            "deps": json.load(open("deps.json")),
            "explores": json.load(open("explores.json"))
        }

    def identify_optimizations(self, intelligence: dict):
        """Step 2: Analyze data to find optimization opportunities"""
        print("[2/5] Identifying optimizations...")

        optimizations = []

        # Find unused fields
        usage_map = intelligence["usage"]["usage_map"]
        for explore, fields in usage_map.items():
            # Get all fields in explore
            field_discovery = self.run_command([
                "lookerctl", "analyze", "explore-fields-local",
                str(self.lookml_dir), explore.split(".")[1],
                "-o", f"fields_{explore.replace('.', '_')}.json"
            ])

            # Compare to usage
            # (fields in explore but not in usage_map are unused)
            # ... AI logic here ...

        # Find orphaned views
        orphaned = self.run_command([
            "lookerctl", "deps", "orphaned",
            str(self.lookml_dir)
        ])

        # ... AI analyzes and creates optimization plan ...

        return optimizations

    def create_baselines(self, explores: list[str]):
        """Step 3: Create baselines before making changes"""
        print("[3/5] Creating baselines...")

        baselines = {}

        for explore in explores:
            # Discover fields
            fields = self.run_command([
                "lookerctl", "analyze", "explore-fields",
                explore, "-o", f"fields_{explore.replace('.', '_')}.json"
            ])

            # Generate query spec (AI logic)
            query_spec = self.generate_query_spec(fields)
            query_file = f"query_{explore.replace('.', '_')}.json"
            with open(query_file, 'w') as f:
                json.dump(query_spec, f)

            # Create baseline
            baseline_file = f"baseline_{explore.replace('.', '_')}.json"
            subprocess.run([
                "lookerctl", "query-test", "baseline", "create",
                explore, "-q", query_file, "-o", baseline_file
            ])

            baselines[explore] = baseline_file

        return baselines

    def execute_optimizations(self, optimizations: list, baselines: dict):
        """Step 4: Make changes and validate"""
        print("[4/5] Executing optimizations...")

        results = []

        for optimization in optimizations:
            # Make changes to LookML files
            self.apply_optimization(optimization)

            # Validate locally (fast!)
            validation = subprocess.run([
                "lookerctl", "validate", "static",
                str(self.lookml_dir)
            ], capture_output=True)

            if validation.returncode != 0:
                print(f"  ✗ Validation failed: {optimization['name']}")
                self.revert_optimization(optimization)
                continue

            # Compare to baseline
            explore = optimization["explore"]
            baseline = baselines[explore]

            comparison = subprocess.run([
                "lookerctl", "query-test", "baseline", "compare",
                explore, "-b", baseline
            ], capture_output=True)

            if comparison.returncode == 0:
                print(f"  ✓ Optimization successful: {optimization['name']}")
                results.append({
                    "optimization": optimization,
                    "status": "success"
                })
            else:
                print(f"  ✗ Baseline comparison failed: {optimization['name']}")
                self.revert_optimization(optimization)
                results.append({
                    "optimization": optimization,
                    "status": "failed"
                })

        return results

    def deploy_and_document(self, results: list):
        """Step 5: Push changes and create golden tests"""
        print("[5/5] Deploying and documenting...")

        # Push to Looker
        subprocess.run([
            "lookerctl", "export", "push",
            self.project_id, str(self.lookml_dir)
        ])

        # Create golden tests for successful optimizations
        for result in results:
            if result["status"] == "success":
                explore = result["optimization"]["explore"]
                query_file = f"query_{explore.replace('.', '_')}.json"
                expected_file = f"expected_{explore.replace('.', '_')}.json"

                # Create golden test
                subprocess.run([
                    "lookerctl", "query-test", "golden", "create",
                    explore,
                    "--name", f"{explore}_optimization",
                    "-q", query_file,
                    "-e", expected_file,
                    "--scope", "permanent"
                ])

        # Commit to git
        subprocess.run(["git", "add", "."])
        subprocess.run([
            "git", "commit", "-m",
            f"AI optimizations: {len([r for r in results if r['status'] == 'success'])} successful"
        ])

        return {
            "total_optimizations": len(results),
            "successful": len([r for r in results if r["status"] == "success"]),
            "failed": len([r for r in results if r["status"] == "failed"])
        }

    def run(self):
        """Execute full optimization pipeline"""
        print("=== AI-Driven LookML Optimization ===\n")

        # 1. Gather intelligence
        intelligence = self.gather_intelligence()

        # 2. Identify optimizations
        optimizations = self.identify_optimizations(intelligence)
        print(f"  Found {len(optimizations)} optimization opportunities")

        if not optimizations:
            print("  No optimizations needed!")
            return

        # 3. Create baselines
        explores_to_test = list(set(opt["explore"] for opt in optimizations))
        baselines = self.create_baselines(explores_to_test)

        # 4. Execute optimizations
        results = self.execute_optimizations(optimizations, baselines)

        # 5. Deploy and document
        summary = self.deploy_and_document(results)

        print(f"\n=== Complete ===")
        print(f"  Successful: {summary['successful']}/{summary['total_optimizations']}")
        print(f"  Failed: {summary['failed']}/{summary['total_optimizations']}")

        return summary

    def generate_query_spec(self, fields: dict) -> dict:
        """AI logic to generate query specification from fields"""
        # Simple example: Take first measure and first 3 dimensions
        dimensions = [f["name"] for f in fields["fields"]["dimensions"][:3]]
        measures = [f["name"] for f in fields["fields"]["measures"][:1]]

        return {
            "fields": dimensions + measures,
            "filters": {},
            "sorts": [f"{measures[0]} desc"] if measures else [],
            "limit": "100"
        }

    def apply_optimization(self, optimization: dict):
        """Apply an optimization to LookML files"""
        # AI implements specific optimization
        pass

    def revert_optimization(self, optimization: dict):
        """Revert an optimization"""
        subprocess.run(["git", "restore", optimization["file"]])


# Usage
if __name__ == "__main__":
    optimizer = LookerOptimizer(
        project_id="my-project",
        lookml_dir=Path("./lookml")
    )
    optimizer.run()
```

### Example 2: Node.js - Usage Analysis

```javascript
const { execSync } = require('child_process');
const fs = require('fs');

class LookerAnalyzer {
  constructor() {
    this.usage = null;
    this.deps = null;
  }

  runCommand(cmd) {
    const output = execSync(cmd, { encoding: 'utf-8' });
    return JSON.parse(output);
  }

  async analyze() {
    // Gather data
    console.log('Analyzing usage...');
    execSync('lookerctl analyze usage -o usage.json');
    this.usage = JSON.parse(fs.readFileSync('usage.json', 'utf-8'));

    console.log('Building dependency graph...');
    execSync('lookerctl deps build ./lookml -o deps.json');
    this.deps = JSON.parse(fs.readFileSync('deps.json', 'utf-8'));

    return this.generateReport();
  }

  generateReport() {
    const report = {
      timestamp: new Date().toISOString(),
      summary: {
        total_explores: Object.keys(this.usage.usage_map).length,
        total_fields_used: Object.values(this.usage.usage_map)
          .reduce((sum, fields) => sum + Object.keys(fields).length, 0),
        total_views: this.deps.statistics.total_views
      },
      recommendations: []
    };

    // Find unused explores
    const allExplores = new Set(
      this.deps.nodes
        .filter(n => n.type === 'explore')
        .map(n => `${n.model}.${n.id}`)
    );

    const usedExplores = new Set(Object.keys(this.usage.usage_map));

    const unusedExplores = [...allExplores].filter(
      e => !usedExplores.has(e)
    );

    if (unusedExplores.length > 0) {
      report.recommendations.push({
        type: 'unused_explores',
        priority: 'medium',
        count: unusedExplores.length,
        explores: unusedExplores,
        action: 'Consider hiding or removing these explores'
      });
    }

    // Find highly-used explores (optimization targets)
    const exploreCounts = Object.entries(this.usage.explore_field_counts)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 10);

    report.recommendations.push({
      type: 'optimization_targets',
      priority: 'high',
      explores: exploreCounts.map(([name, count]) => ({
        name,
        field_count: count
      })),
      action: 'Optimize these high-usage explores for performance'
    });

    return report;
  }
}

// Usage
const analyzer = new LookerAnalyzer();
analyzer.analyze().then(report => {
  console.log(JSON.stringify(report, null, 2));
  fs.writeFileSync('analysis_report.json', JSON.stringify(report, null, 2));
});
```

## AI Decision Making Framework

### Phase 1: Information Gathering

```python
def gather_all_information():
    """Collect all available data about the LookML project"""
    return {
        "lookml_files": export_all_lookml(),
        "usage_data": analyze_usage(),
        "dependencies": build_dependency_graph(),
        "explores": list_all_explores(),
        "current_performance": benchmark_key_explores()
    }
```

**Outputs**:
- All LookML files locally
- `usage.json` - field usage mapping
- `deps.json` - dependency graph
- `explores.json` - explore list
- Performance baselines

### Phase 2: Analysis & Planning

```python
def analyze_and_plan(information):
    """Analyze data and create optimization plan"""
    opportunities = []

    # 1. Find unused fields
    for explore, fields in information["usage_data"]["usage_map"].items():
        all_fields = get_explore_fields(explore)
        unused = set(all_fields) - set(fields.keys())
        if unused:
            opportunities.append({
                "type": "hide_unused_fields",
                "explore": explore,
                "fields": list(unused),
                "priority": "low",
                "risk": "low"
            })

    # 2. Find orphaned views
    orphaned = find_orphaned_views(information["dependencies"])
    if orphaned:
        opportunities.append({
            "type": "remove_orphaned_views",
            "views": orphaned,
            "priority": "medium",
            "risk": "low"
        })

    # 3. Identify slow explores
    for explore, perf in information["current_performance"].items():
        if perf["runtime_seconds"] > 10:
            opportunities.append({
                "type": "optimize_performance",
                "explore": explore,
                "current_runtime": perf["runtime_seconds"],
                "target_runtime": perf["runtime_seconds"] * 0.7,  # 30% improvement
                "priority": "high",
                "risk": "medium"
            })

    # Sort by priority and risk
    return sorted(opportunities, key=lambda x: (
        {"high": 0, "medium": 1, "low": 2}[x["priority"]],
        {"high": 2, "medium": 1, "low": 0}[x["risk"]]
    ))
```

### Phase 3: Safe Execution

```python
def execute_optimization_safely(optimization):
    """Execute optimization with full validation"""

    # 1. Analyze impact
    affected_explores = analyze_impact(optimization)

    # 2. Create baselines for all affected explores
    baselines = {}
    for explore in affected_explores:
        baselines[explore] = create_baseline(explore)

    # 3. Make changes
    apply_optimization(optimization)

    # 4. Validate locally (fast!)
    if not validate_locally():
        revert_changes()
        return {"status": "validation_failed"}

    # 5. Compare to all baselines
    all_passed = True
    for explore, baseline in baselines.items():
        if not compare_to_baseline(explore, baseline):
            all_passed = False
            break

    if not all_passed:
        revert_changes()
        return {"status": "baseline_failed"}

    # 6. Success! Push and create golden test
    push_to_looker()
    create_golden_test(optimization)

    return {"status": "success"}
```

## Best Practices for AI Integration

### 1. Always Validate Before Deploying

```python
# ✅ Good: Validate → Test → Deploy
modify_lookml()
if validate_locally() and compare_to_baseline():
    deploy()

# ❌ Bad: Deploy without validation
modify_lookml()
deploy()  # Hope for the best!
```

### 2. Use Local Validation for Speed

```python
# ✅ Good: Fast local validation during iteration
for attempt in range(10):
    modify_lookml()
    if validate_locally():  # 600ms
        break

# Final check with API
validate_with_api()  # 40s, but accurate

# ❌ Bad: API validation every iteration
for attempt in range(10):
    modify_lookml()
    validate_with_api()  # 400s total!
```

### 3. Create Baselines for All Affected Explores

```python
# ✅ Good: Test everything that might be affected
affected = analyze_impact(view_to_change)
for explore in affected:
    create_baseline(explore)

modify_view()

for explore in affected:
    compare_to_baseline(explore)

# ❌ Bad: Only test one explore
create_baseline("main_explore")
modify_view()
compare_to_baseline("main_explore")  # Might break others!
```

### 4. Use Appropriate Tolerances

```python
# ✅ Good: Different tolerances for different data
compare_to_baseline(
    "financial_metrics",
    tolerance=0  # Exact for money
)

compare_to_baseline(
    "approximate_stats",
    tolerance=0.05  # 5% for estimates
)

# ❌ Bad: Same tolerance for everything
compare_to_baseline("financial_metrics", tolerance=0.1)  # Too loose!
```

### 5. Document Everything

```python
# ✅ Good: Create golden tests for all changes
for optimization in successful_optimizations:
    create_golden_test(
        optimization.explore,
        name=f"{optimization.type}_{timestamp}",
        scope="permanent"
    )

# ❌ Bad: No tests, no documentation
# Changes deployed with no record
```

## Common AI Use Cases

### Use Case 1: Auto-Hide Unused Fields

```python
def hide_unused_fields():
    usage = load_usage_json()

    for explore, used_fields in usage["usage_map"].items():
        all_fields = discover_explore_fields(explore)

        # Find unused fields
        unused = set(all_fields) - set(used_fields.keys())

        if unused:
            # Create baseline
            baseline = create_baseline(explore)

            # Hide unused fields
            for field in unused:
                add_hidden_yes_to_field(field)

            # Validate nothing broke
            if compare_to_baseline(explore, baseline):
                print(f"✓ Successfully hid {len(unused)} unused fields in {explore}")
            else:
                print(f"✗ Failed - reverting changes")
                revert()
```

### Use Case 2: Auto-Optimize Slow Explores

```python
def optimize_slow_explores():
    explores = find_working_explore()

    for explore in explores:
        # Baseline current performance
        baseline = create_baseline(explore)
        current_runtime = baseline["performance"]["runtime_seconds"]

        if current_runtime > 10:  # Slow explore
            # Try optimizations
            optimizations = [
                add_persistent_derived_table,
                add_indexes,
                optimize_sql
            ]

            for opt in optimizations:
                opt(explore)

                if validate_locally():
                    new_baseline = create_baseline(explore)
                    new_runtime = new_baseline["performance"]["runtime_seconds"]

                    improvement = (current_runtime - new_runtime) / current_runtime

                    if improvement > 0.3:  # 30% faster
                        print(f"✓ {opt.__name__} improved {explore} by {improvement:.0%}")
                        create_golden_test(explore)
                        break
                    else:
                        revert()
```

### Use Case 3: Auto-Remove Orphaned Views

```python
def remove_orphaned_views():
    deps = build_dependency_graph()
    orphaned = find_orphaned_views(deps)

    if not orphaned:
        print("No orphaned views found")
        return

    # Verify they're truly unused
    usage = load_usage_json()

    for view in orphaned:
        # Check if view appears in any usage
        if not view_referenced_anywhere(view, usage):
            # Safe to remove
            remove_view_file(view)
            print(f"✓ Removed orphaned view: {view}")
        else:
            print(f"⚠ View {view} appears orphaned but is referenced - keeping")
```

## Summary

The Looker CLI is designed for AI automation:

✅ **Every output is JSON** - Machine-readable
✅ **Every operation is scriptable** - No manual steps
✅ **Fast local validation** - 66x faster iteration
✅ **Scientific testing** - Verify correctness automatically
✅ **Complete visibility** - Export everything

**The result**: AI can optimize LookML automatically with the same safety and validation as human developers.

## Next Steps

- **[CLI Reference](./CLI_REFERENCE.md)** - Complete command reference
- **[Query Testing](./QUERY_TESTING.md)** - Deep dive on testing
- **[Workflows](./WORKFLOWS.md)** - Common patterns
- **[Examples](./EXAMPLES.md)** - Real-world examples

---

**Remember**: Use the CLI's JSON outputs to inform AI decisions, validate all changes, and create golden tests to prevent regressions.
