# Query Testing Guide

Scientific testing for LookML changes using baselines, AB tests, and golden tests.

## Why Query Testing?

When you optimize LookML (views, explores, SQL), you need to validate:

1. **Correctness** - Does the query still return correct results?
2. **Performance** - Did the optimization actually improve performance?
3. **No Regressions** - Did we break existing functionality?

Traditional approach:
- Make changes
- Hope for the best
- Find out later if something broke

**Scientific approach**:
- Capture state before changes (baseline)
- Make changes
- Compare after to before (AB test)
- Create permanent tests (golden tests)
- **Know with certainty** that changes are correct

## Three Testing Approaches

| Type | Use Case | Persistence |
|------|----------|-------------|
| **Baseline** | One-time AB test before/after changes | Temporary |
| **AB Comparison** | Compare current state to baseline | On-demand |
| **Golden Test** | Permanent regression prevention | Permanent (git) |

## Baselines: Capture State

A baseline is a **snapshot** of query results and performance at a point in time.

### Creating a Baseline

#### Step 1: Find a Working Explore

```bash
# List all explores and choose one
lookerctl analyze list-explores | grep -i "orders"
```

**Why this matters**: Not all explores have accessible data connections. This step finds one that does.

#### Step 2: Discover Available Fields

```bash
# Get fields that exist in the explore
lookerctl analyze explore-fields analytics.billing \
  -o fields.json
```

**Output** (`fields.json`):
```json
{
  "explore": "billing_data",
  "fields": {
    "dimensions": [
      {"name": "billing_data.billingamount", "type": "number"},
      {"name": "billing_data.cloudprovider", "type": "string"},
      {"name": "billing_data.starttime_date", "type": "date"}
    ],
    "measures": [
      {"name": "billing_data.count", "type": "number"}
    ]
  }
}
```

**AI reads this to know**: What fields exist and their types.

#### Step 3: Create Query Specification

Create `query.json` using discovered fields:

```json
{
  "fields": [
    "billing_data.billingamount",
    "billing_data.cloudprovider",
    "billing_data.count"
  ],
  "filters": {
    "billing_data.starttime_date": "30 days"
  },
  "sorts": ["billing_data.count desc"],
  "limit": "10"
}
```

**Query spec rules**:
- Use fields from `fields.json`
- Reasonable limit (10-500 rows)
- Representative of real dashboard usage
- Include filters that make sense

#### Step 4: Test the Query (Dry-Run)

```bash
lookerctl query-test baseline create analytics.billing \
  -q query.json --dry-run
```

**Output**:
```
DRY RUN - Validating query for analytics.billing

✓ Query validation successful!
  Rows returned: 10
  Runtime: 58.66s
  Status: complete

Note: Baseline not created (dry-run mode)
      Remove --dry-run to create baseline
```

**Purpose**: Verify query works before creating baseline.

#### Step 5: Create Baseline

```bash
lookerctl query-test baseline create analytics.billing \
  -q query.json -o baseline_before.json
```

**Output** (`baseline_before.json`):
```json
{
  "explore": "analytics.billing",
  "query": {
    "fields": ["billing_data.billingamount", "billing_data.count"],
    "filters": {"billing_data.starttime_date": "30 days"},
    "sorts": ["billing_data.count desc"],
    "limit": "10"
  },
  "results": [
    {
      "billing_data.billingamount": 12345.67,
      "billing_data.cloudprovider": "AWS",
      "billing_data.count": 150
    },
    {
      "billing_data.billingamount": 9876.54,
      "billing_data.cloudprovider": "GCP",
      "billing_data.count": 120
    }
    // ... 8 more rows
  ],
  "row_count": 10,
  "performance": {
    "runtime_seconds": 53.68,
    "status": "complete",
    "cache_hit": false
  },
  "metadata": {
    "created_at": "2025-10-11T18:15:23.123456+00:00",
    "git_branch": "main",
    "git_commit": "abc123def456"
  }
}
```

**What's captured**:
- ✅ Query specification (reproducible)
- ✅ Actual results (data correctness)
- ✅ Row count (completeness)
- ✅ Runtime (performance)
- ✅ Git context (traceability)

## AB Testing: Compare Before/After

Now make your LookML changes and compare.

### The AB Testing Workflow

```bash
# 1. Create baseline BEFORE changes
lookerctl query-test baseline create model.explore \
  -q query.json -o before.json

# 2. Make your LookML changes
# - Optimize derived table SQL
# - Add indexes
# - Refactor joins
# - Add persistence

# 3. Validate syntax
lookerctl validate static ./lookml

# 4. Push changes to Looker
lookerctl export push my-project ./lookml

# 5. Compare AFTER changes to baseline
lookerctl query-test baseline compare model.explore \
  -b before.json
```

### Understanding Comparison Results

#### Scenario 1: Perfect - Data Identical, Performance Improved

```
┏━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Metric      ┃ Baseline ┃ Current ┃ Change           ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ Row Count   │ 10       │ 10      │ ✓ +0             │
│ Runtime (s) │ 53.68    │ 20.34   │ ✓ -33.34s (-62%) │
└─────────────┴──────────┴─────────┴──────────────────┘

✓ Comparison PASSED

Performance improved by 62% with no data changes!
```

**Interpretation**:
- ✅ **PASSED** - Data is identical
- ⚡ **62% faster** - Optimization worked!
- ✅ **Safe to merge**

#### Scenario 2: Good - Data Identical, Performance Unchanged

```
┏━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ Metric      ┃ Baseline ┃ Current ┃ Change         ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ Row Count   │ 10       │ 10      │ ✓ +0           │
│ Runtime (s) │ 53.68    │ 53.72   │ ✓ +0.04s (+0%) │
└─────────────┴──────────┴─────────┴──────────────────┘

✓ Comparison PASSED

Performance unchanged, data correct.
```

**Interpretation**:
- ✅ **PASSED** - Data is identical
- ≈ **Same performance** - Refactoring safe but didn't optimize
- ✅ **Safe to merge** (cosmetic changes, refactoring)

#### Scenario 3: Warning - Data Identical, Performance Worse

```
┏━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Metric      ┃ Baseline ┃ Current ┃ Change          ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ Row Count   │ 10       │ 10      │ ✓ +0            │
│ Runtime (s) │ 53.68    │ 78.23   │ ⚠ +24.55s (+46%)│
└─────────────┴──────────┴─────────┴─────────────────┘

✓ Comparison PASSED

⚠ Warning: Performance degraded by 46%
```

**Interpretation**:
- ✅ **PASSED** - Data is correct
- ⚠️ **46% slower** - Changes made it worse
- ⚠️ **Reconsider changes** or investigate why slower

#### Scenario 4: Failure - Data Changed

```
┏━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Metric      ┃ Baseline ┃ Current ┃ Change          ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ Row Count   │ 10       │ 8       │ ✗ -2            │
│ Runtime (s) │ 53.68    │ 45.12   │ ✓ -8.56s (-16%) │
└─────────────┴──────────┴─────────┴─────────────────┘

Data Differences Found:
  2 row(s) missing from current results
  0 row(s) added in current results

Row 1 differences:
  billing_data.count:
    Baseline: 150
    Current:  148
    Delta:    -2

✗ Comparison FAILED

Data changed! Review changes before merging.
```

**Interpretation**:
- ✗ **FAILED** - Data is different!
- ⚡ **16% faster** - But correctness is broken
- ❌ **DO NOT MERGE** - Fix data correctness first

**Common causes**:
- Join logic changed
- Filter logic changed
- Aggregation changed
- Date/time logic issues

### Tolerance Settings

```bash
# Strict - no tolerance (for exact data)
lookerctl query-test baseline compare model.explore \
  -b baseline.json --tolerance 0

# Default - 1% tolerance (for financial data)
lookerctl query-test baseline compare model.explore \
  -b baseline.json --tolerance 0.01

# Lenient - 5% tolerance (for approximate metrics)
lookerctl query-test baseline compare model.explore \
  -b baseline.json --tolerance 0.05
```

**Use strict (0) for**:
- Financial data
- Counts (should be exact)
- Critical metrics

**Use lenient (>0.01) for**:
- Approximate aggregations
- Floating point calculations
- Sampling-based metrics

## Golden Tests: Permanent Regression Prevention

Golden tests are **permanent tests** that run in CI/CD to prevent regressions.

### Creating a Golden Test

#### Step 1: Define Expected Results

Create `expected.json`:

```json
{
  "row_count": 10,
  "schema": {
    "billing_data.billingamount": "number",
    "billing_data.cloudprovider": "string",
    "billing_data.count": "number"
  },
  "data": [
    {
      "billing_data.billingamount": 12345.67,
      "billing_data.cloudprovider": "AWS",
      "billing_data.count": 150
    }
    // Optional: Include expected data for first few rows
  ]
}
```

**Three validation levels**:

1. **Row count only**: Just check number of rows
   ```json
   {
     "row_count": 10
   }
   ```

2. **Row count + schema**: Check structure
   ```json
   {
     "row_count": 10,
     "schema": {
       "field1": "number",
       "field2": "string"
     }
   }
   ```

3. **Row count + schema + data**: Check exact values
   ```json
   {
     "row_count": 10,
     "schema": { /* ... */ },
     "data": [ /* expected rows */ ]
   }
   ```

#### Step 2: Create Golden Test

```bash
lookerctl query-test golden create analytics.billing \
  --name "billing_smoke_test" \
  -q query.json \
  -e expected.json \
  --scope permanent
```

**Output**:
```
✓ Created golden test: billing_smoke_test
  Saved to: golden_tests/billing_smoke_test.json
```

**Test file** (`golden_tests/billing_smoke_test.json`):
```json
{
  "name": "billing_smoke_test",
  "explore": "analytics.billing",
  "query": { /* query spec */ },
  "expected": { /* expected results */ },
  "tolerance": {
    "numeric_tolerance": 0.01,
    "allow_extra_rows": false,
    "allow_missing_rows": false
  },
  "metadata": {
    "created_at": "2025-10-11T18:25:29.928318+00:00",
    "scope": "permanent",
    "created_by": "looker-cli"
  }
}
```

#### Step 3: Run Golden Tests

```bash
# Run all tests
lookerctl query-test golden run

# Run specific test
lookerctl query-test golden run --name billing_smoke_test

# Run and save results
lookerctl query-test golden run -o test_results.json
```

**Output**:
```
Running 3 golden test(s)

  Test: billing_smoke_test
  Rows: 10
  Runtime: 52.71s
  Status: ✓ PASSED

  Test: user_metrics_test
  Rows: 50
  Runtime: 23.45s
  Status: ✓ PASSED

  Test: revenue_validation
  Rows: 100
  Runtime: 67.89s
  Status: ✗ FAILED
  Failures:
    • Row 5, field users.count: expected 150, got 148

Summary
  Total: 3
  Passed: 2
  Failed: 1
```

**Exit code**: Non-zero if any tests fail (for CI/CD).

### Test Scopes

#### Permanent Scope

```bash
--scope permanent
```

**Use for**:
- Core business metrics
- Production explores
- Critical dashboards
- Regression prevention

**Stored in**: `golden_tests/` (commit to git)

**Run in**: CI/CD pipelines

#### Feature Branch Scope

```bash
--scope feature_branch
```

**Use for**:
- New feature development
- Experimental explores
- Temporary validation
- Branch-specific tests

**Stored in**: `golden_tests/` but deleted after merge

### Managing Golden Tests

```bash
# List all tests
lookerctl query-test golden list

# Delete a test
lookerctl query-test golden delete --name old_test
```

## Complete Workflow Examples

### Example 1: Performance Optimization

**Goal**: Optimize slow explore by 30%

```bash
# 1. Find working explore
lookerctl analyze list-explores | grep -i "orders"

# 2. Discover fields
lookerctl analyze explore-fields analytics.billing \
  -o fields.json

# 3. Create query spec (query.json) using fields
cat > query.json << 'JSON'
{
  "fields": ["billing_data.billingamount", "billing_data.count"],
  "filters": {"billing_data.starttime_date": "30 days"},
  "sorts": ["billing_data.count desc"],
  "limit": "100"
}
JSON

# 4. Create baseline BEFORE
lookerctl query-test baseline create analytics.billing \
  -q query.json -o before.json

# Baseline: 100 rows, 67.23s

# 5. Make optimizations
# - Add persistent_derived_table
# - Add indexes
# - Optimize SQL

# 6. Validate locally
lookerctl validate static ./lookml

# 7. Push changes
lookerctl export push my-project ./lookml

# 8. Compare AFTER
lookerctl query-test baseline compare analytics.billing \
  -b before.json

# Result: 100 rows, 31.45s (-53% faster!)

# 9. Success! Create golden test
cat > expected.json << 'JSON'
{
  "row_count": 100,
  "schema": {
    "billing_data.billingamount": "number",
    "billing_data.count": "number"
  }
}
JSON

lookerctl query-test golden create analytics.billing \
  --name "billing_performance_test" \
  -q query.json \
  -e expected.json \
  --scope permanent

# 10. Commit
git add . && git commit -m "Optimized billing_data explore - 53% faster"
```

### Example 2: Safe Refactoring

**Goal**: Refactor view without breaking anything

```bash
# 1. Analyze impact
lookerctl deps impact users ./lookml

# Shows: 5 explores affected

# 2. For each affected explore, create baseline
lookerctl query-test baseline create sales.user_orders \
  -q query1.json -o baseline1.json

lookerctl query-test baseline create analytics.user_cohorts \
  -q query2.json -o baseline2.json

# ... for all 5 explores

# 3. Make refactoring changes

# 4. Validate locally
lookerctl validate static ./lookml

# 5. Compare to ALL baselines
lookerctl query-test baseline compare sales.user_orders -b baseline1.json
lookerctl query-test baseline compare analytics.user_cohorts -b baseline2.json
# ... for all 5

# 6. If ALL pass, refactoring is safe
lookerctl export push my-project ./lookml
```

### Example 3: Adding Regression Tests

**Goal**: Create golden tests for all critical explores

```bash
# 1. Identify critical explores from usage
lookerctl analyze usage -o usage.json

# AI reads usage.json to find:
# - Top 10 explores by field usage
# - Explores used in >5 dashboards

# 2. For each critical explore:

# 2a. Discover fields
lookerctl analyze explore-fields sales.user_orders -o fields.json

# 2b. Create representative query
# (AI generates query.json from fields.json)

# 2c. Run query to get current results
lookerctl query-test baseline create sales.user_orders \
  -q query.json -o baseline.json --dry-run

# 2d. Create expected from current state
# (Use baseline as source of truth)

# 2e. Create golden test
lookerctl query-test golden create sales.user_orders \
  --name "user_orders_regression" \
  -q query.json \
  -e expected.json \
  --scope permanent

# 3. Now tests run in CI/CD to prevent regressions!
```

## CI/CD Integration

### In Your CI Pipeline

```bash
#!/bin/bash
# ci/test-lookml.sh

# Source environment
source .env

# Run all golden tests
lookerctl query-test golden run --output test-results.json

# Check exit code
if [ $? -ne 0 ]; then
  echo "❌ Golden tests failed"
  cat test-results.json
  exit 1
else
  echo "✅ All golden tests passed"
  exit 0
fi
```

### GitHub Actions Example

```yaml
name: LookML Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Run Golden Tests
        env:
          LOOKERSDK_BASE_URL: ${{ secrets.LOOKER_BASE_URL }}
          LOOKERSDK_CLIENT_ID: ${{ secrets.LOOKER_CLIENT_ID }}
          LOOKERSDK_CLIENT_SECRET: ${{ secrets.LOOKER_CLIENT_SECRET }}
        run: |
          lookerctl query-test golden run
```

## Best Practices

### 1. Test Representative Queries

❌ **Don't**: Test simple queries
```json
{
  "fields": ["users.count"],
  "limit": "1"
}
```

✅ **Do**: Test realistic queries
```json
{
  "fields": ["users.count", "users.city", "orders.total_revenue", "orders.avg_order_value"],
  "filters": {"orders.created_year": "2024", "users.state": "California"},
  "sorts": ["orders.total_revenue desc"],
  "limit": "100"
}
```

### 2. Set Appropriate Tolerances

```bash
# Financial data - precise
--tolerance 0.01

# Approximate metrics - lenient
--tolerance 1.0

# Counts - strict
--tolerance 0
```

### 3. Version Baselines

```bash
# Name baselines descriptively
baselines/
├── user_orders_v1_before.json
├── user_orders_v1_after.json
├── user_orders_v2_before.json
└── user_orders_v2_after.json
```

### 4. Use Dry-Run First

```bash
# Always dry-run before creating baseline
lookerctl query-test baseline create model.explore \
  -q query.json --dry-run

# If successful, create baseline
lookerctl query-test baseline create model.explore \
  -q query.json -o baseline.json
```

### 5. Golden Tests for Top Explores

```bash
# Find top explores
lookerctl analyze usage -o usage.json

# AI identifies top 10
# Create golden test for each
```

## Troubleshooting

### Issue: "View Not Found" when creating baseline

**Cause**: Incorrect model.explore format

**Solution**:
```bash
# List all explores
lookerctl analyze list-explores | grep -i "my_explore"

# Use exact format shown
lookerctl query-test baseline create EXACT.FORMAT -q query.json
```

### Issue: Query returns 0 rows

**Cause**: Filters too restrictive or no data

**Solution**:
- Adjust filters in query.json
- Try different time ranges
- Use dry-run to test: `--dry-run`

### Issue: Performance varies between runs

**Cause**: Caching, concurrent queries

**Solution**:
- Run multiple times and average
- Consider caching in interpretation
- Use larger datasets for more stable timing

### Issue: Data differences on floating point

**Cause**: Floating point precision

**Solution**:
```bash
# Increase tolerance for floating point fields
--tolerance 0.01  # 1% tolerance
```

## Summary

Query testing enables **scientific LookML development**:

✅ **Correctness** - Verify data is identical before/after
✅ **Performance** - Measure actual improvements
✅ **Regression Prevention** - Golden tests catch breaking changes
✅ **Confidence** - Know changes are safe
✅ **Automation** - CI/CD integration

**The result**: Faster, safer LookML optimization with full confidence.

## Next Steps

- **[AI Integration](./AI_INTEGRATION.md)** - AI-driven testing workflows
- **[Workflows](./WORKFLOWS.md)** - Common testing patterns
- **[Examples](./EXAMPLES.md)** - Real-world examples
- **[CLI Reference](./CLI_REFERENCE.md)** - Complete command reference

---

**Remember**: Test before changing, compare after changing, automate to prevent regressions.
