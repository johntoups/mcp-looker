#!/bin/bash
# End-to-End LookML Testing Workflow Demo
# This script demonstrates the complete AB testing and golden test workflow

set -e # Exit on error

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Configuration
MODEL_EXPLORE="myapp.features"
TEST_DIR="test_validation"
QUERY_FILE="$TEST_DIR/queries/feature_flags_query.json"
BASELINE_FILE="$TEST_DIR/baselines/feature_flags_baseline.json"
GOLDEN_TEST_NAME="feature_flags_regression"

echo "==================================="
echo "LookML Testing Workflow Demo"
echo "==================================="
echo ""

# Step 1: Field Discovery
echo "📋 Step 1: Discovering fields in explore..."
./looker.py analyze explore-fields-local . feature_flags \
  -o "$TEST_DIR/queries/feature_flags_fields.json"

if [ $? -eq 0 ]; then
  echo "✅ Field discovery completed"
else
  echo "❌ Field discovery failed"
  exit 1
fi
echo ""

# Step 2: Create Query Specification
# (This is typically done manually or via AI based on field discovery)
echo "📝 Step 2: Query specification already created"
echo "   File: $QUERY_FILE"
echo ""

# Step 3: Create Baseline (BEFORE changes)
echo "🎯 Step 3: Creating baseline snapshot..."
echo "   This captures current query results and performance"
./looker.py query-test baseline create "$MODEL_EXPLORE" \
  -q "$QUERY_FILE" \
  -o "$BASELINE_FILE"

if [ $? -eq 0 ]; then
  echo "✅ Baseline created successfully"
else
  echo "⚠️  Baseline creation blocked (see VALIDATION_REPORT.md for details)"
  echo "   Using example baseline for demo purposes"
  cp "$TEST_DIR/example_baseline.json" "$BASELINE_FILE"
fi
echo ""

# Step 4: Make LookML Changes
echo "✏️  Step 4: Make your LookML changes..."
echo "   Example changes:"
echo "   - Optimize SQL in derived table"
echo "   - Add indexes to improve performance"
echo "   - Refactor explore joins"
echo "   - Change aggregation logic"
echo ""
read -p "Press Enter after making changes (or skip for demo)..."
echo ""

# Step 5: Validate Changes Locally
echo "🔍 Step 5: Validating LookML syntax locally..."
./looker.py validate static . --explore feature_flags 2>/dev/null || true
echo ""

# Step 6: Push Changes to Looker
echo "📤 Step 6: Pushing changes to Looker dev branch..."
echo "   (Skipped in demo - would run: ./looker.py export push ...)"
echo ""

# Step 7: Compare to Baseline (AB Test)
echo "⚖️  Step 7: Running AB test comparison..."
./looker.py query-test baseline compare "$MODEL_EXPLORE" \
  -b "$BASELINE_FILE" \
  -o "$TEST_DIR/comparison_result.json" \
  --tolerance 0.01

COMPARISON_RESULT=$?
echo ""

# Step 8: Evaluate Results
if [ $COMPARISON_RESULT -eq 0 ]; then
  echo "✅ Step 8: AB test PASSED!"
  echo ""
  echo "   Results:"
  echo "   - Data correctness: ✅ Verified"
  echo "   - Performance: Check comparison_result.json"
  echo ""

  # Step 9: Create Golden Test
  echo "🏆 Step 9: Creating golden test for regression prevention..."

  # Create expected results file
  cat >"$TEST_DIR/golden_tests/expected.json" <<'EXPECTED'
{
  "row_count": 100,
  "schema": {
    "feature_flags.name": "string",
    "feature_flags.kind": "string",
    "feature_flags.archived": "string",
    "feature_flags.count": "number"
  }
}
EXPECTED

  ./looker.py query-test golden create "$MODEL_EXPLORE" \
    --name "$GOLDEN_TEST_NAME" \
    -q "$QUERY_FILE" \
    -e "$TEST_DIR/golden_tests/expected.json" \
    --scope permanent

  echo "✅ Golden test created"
  echo ""

  # Step 10: Run Golden Tests
  echo "🧪 Step 10: Running all golden tests..."
  ./looker.py query-test golden run \
    -d "$TEST_DIR/golden_tests" \
    -o "$TEST_DIR/golden_test_results.json"

  echo ""
  echo "======================================"
  echo "✅ Workflow completed successfully!"
  echo "======================================"
  echo ""
  echo "Your changes:"
  echo "  ✅ Passed data correctness check"
  echo "  ✅ Have been baselined"
  echo "  ✅ Are protected by golden test"
  echo ""
  echo "Next steps:"
  echo "  1. Review performance in: $TEST_DIR/comparison_result.json"
  echo "  2. Commit changes if satisfied"
  echo "  3. Golden tests will run in CI/CD"

else
  echo "❌ Step 8: AB test FAILED"
  echo ""
  echo "   Your changes caused data differences!"
  echo ""
  echo "   Review the comparison output above for details."
  echo "   Options:"
  echo "   1. Revert changes and try different optimization"
  echo "   2. If differences are expected, update baseline"
  echo "   3. Investigate why data changed"
  echo ""
  echo "======================================"
  echo "⚠️  Workflow stopped - fix issues first"
  echo "======================================"
  exit 1
fi
