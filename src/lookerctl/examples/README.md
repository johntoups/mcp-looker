# Examples Directory

Real working examples from end-to-end testing and validation.

## What's Here

This directory contains **real, tested examples** that demonstrate working usage of the Looker CLI:

### 📊 Baselines (`baselines/`)
Real baseline files from successful AB testing:
- `billing_data_BEFORE.json` - Baseline before optimization
- `billing_data_AFTER.json` - Baseline after optimization  
- `billing_data_TEST.json` - Test baseline

**Use these as**: Templates for your own baseline files.

### 🔍 Queries (`queries/`)
Real query specifications that work:
- `billing_data_query.json` - Working query for analytics.billing
- `feature_flags_query.json` - Example feature flags query
- `feature_flags_fields.json` - Field discovery output (138 fields)
- Plus more examples

**Use these as**: Templates for creating your own query specs.

### ✅ Golden Tests (`golden_tests/`)
Real golden test files:
- `billing_test_expected.json` - Expected results format

**Use these as**: Templates for regression tests.

### 📝 Example Files
- `example_baseline.json` - Annotated baseline format
- `example_comparison.json` - AB test comparison result
- `example_golden_test.json` - Complete golden test structure

### 🎬 Scripts
- `workflow_demo.sh` - End-to-end workflow demonstration

## Working Explore

**Proven to work**: `analytics.billing`

This explore was tested end-to-end and confirmed working:
- ✅ Field discovery works
- ✅ Query execution works (10 rows, ~53s)
- ✅ Baseline creation works
- ✅ AB comparison works
- ✅ Golden tests work

## Usage

### Create Your First Baseline

```bash
# 1. Use the working explore
MODEL_EXPLORE="analytics.billing"

# 2. Use example query as template
cp examples/queries/billing_data_query.json my_query.json

# 3. Create baseline
lookerctl query-test baseline create $MODEL_EXPLORE \
  -q my_query.json -o my_baseline.json
```

### Run AB Test

```bash
# 1. Create baseline before changes
lookerctl query-test baseline create $MODEL_EXPLORE \
  -q my_query.json -o before.json

# 2. Make changes to LookML

# 3. Compare after changes
lookerctl query-test baseline compare $MODEL_EXPLORE \
  -b before.json
```

### Create Golden Test

```bash
# Use example as template
cp examples/golden_tests/billing_test_expected.json expected.json

# Create test
lookerctl query-test golden create $MODEL_EXPLORE \
  --name "my_regression_test" \
  -q my_query.json \
  -e expected.json \
  --scope permanent
```

## Example File Formats

### Query Specification

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

### Baseline File

```json
{
  "explore": "analytics.billing",
  "query": { /* query spec */ },
  "results": [ /* actual data */ ],
  "row_count": 10,
  "performance": {
    "runtime_seconds": 53.68,
    "status": "complete"
  },
  "metadata": {
    "created_at": "2025-10-11T...",
    "git_branch": "main"
  }
}
```

### Expected Results

```json
{
  "row_count": 10,
  "schema": {
    "billing_data.billingamount": "number",
    "billing_data.cloudprovider": "string",
    "billing_data.count": "number"
  }
}
```

## What These Prove

✅ **End-to-end workflow validated** - All commands work together
✅ **Real data tested** - Not just mocked examples
✅ **AB testing works** - Performance comparison successful
✅ **Golden tests work** - Regression prevention validated

## Historical Context

These examples come from comprehensive testing on 2025-10-11 that:
1. Found a working explore automatically
2. Discovered 78 dimensions and 2 measures
3. Created baselines with real query results
4. Compared before/after states successfully
5. Validated golden test creation and execution

See `lookerctl/docs/QUERY_TESTING.md` for complete guide.

---

**Last Updated**: 2025-10-11
**Status**: All examples tested and working
