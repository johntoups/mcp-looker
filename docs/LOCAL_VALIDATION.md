# Local Validation Guide

Fast local validation using the LookML Runtime Graph (66x faster than API).

## Quick Start

```bash
# Validate entire project (600ms!)
lookerctl validate static ./lookml

# Validate specific view
lookerctl validate static ./lookml --view users

# Validate specific explore
lookerctl validate static ./lookml --explore user_orders

# Discover explore fields locally
lookerctl analyze explore-fields-local ./lookml user_orders -o fields.json
```

## Performance

| Operation | API Method | Local Graph | Speedup |
|-----------|-----------|-------------|---------|
| Validate project | 40s | 600ms | **66x faster** |
| Field discovery | 2s | 100ms | **20x faster** |

## What It Validates

✅ Field references (`${view.field}`, `${field}`)
✅ View existence (extends, joins)
✅ Explore structure
✅ Dependency structure
✅ Circular dependencies

❌ SQL correctness (use API validation for final check)
❌ Table existence
❌ Complex Liquid templating

## When to Use

### Local Validation (Fast)

Use `validate static` for:
- Rapid iteration during development
- AI optimization loops
- Offline work
- Quick error checking

### API Validation (Accurate)

Use `validate local` for:
- Final validation before merge
- SQL correctness checks
- Production deployment
- Authoritative validation

## How It Works

1. **Parse** - All .lkml files parsed using `lkml` library
2. **Build Graph** - In-memory NetworkX graph of dependencies
3. **Resolve** - View inheritance chains resolved
4. **Validate** - Field references checked against graph
5. **Return** - Errors with file/line numbers

## Example Output

```
Parsing LookML project: ./lookml

✓ Loaded 145 views, 42 explores, 3 models

Validating all views and explores...

Found 3 validation error(s):

  views/orders.view.lkml:45 - Field 'total_amount' not found in view 'users'
  views/users.view.lkml:78 - View 'user_facts' not found (referenced in ${user_facts.lifetime_value})
  explores/sales.explore.lkml:12 - Joined view 'inventory' not found in explore 'orders'
```

## Field Discovery

```bash
# Discover fields locally (no API)
lookerctl analyze explore-fields-local ./lookml user_orders -o fields.json
```

**Output** (`fields.json`):
```json
{
  "explore": "user_orders",
  "fields": {
    "dimensions": [
      {"name": "users.id", "type": "number", "description": "User ID"},
      {"name": "orders.total", "type": "number", "description": "Order total"}
    ],
    "measures": [
      {"name": "users.count", "type": "count"},
      {"name": "orders.total_revenue", "type": "sum"}
    ]
  }
}
```

Resolves:
- Base view fields (with extends)
- Joined view fields
- Field scoping rules
- Hidden fields (optional)

## Best Practices

### 1. Use During Development

```bash
# Fast iteration
while developing:
    edit files
    lookerctl validate static ./lookml  # 600ms

# Final check
lookerctl validate local my-project ./lookml  # 40s
```

### 2. Combine with Field Discovery

```bash
# 1. Discover fields locally
lookerctl analyze explore-fields-local ./lookml user_orders -o fields.json

# 2. Generate query using fields
# (AI reads fields.json)

# 3. Create baseline
lookerctl query-test baseline create model.explore -q query.json -o baseline.json
```

### 3. Cache Project Object (Programmatic)

```python
# ✅ Good: Load once
project = LookMLProject(Path("./lookml"))
for file in changed_files:
    project.validate_view(file)

# ❌ Bad: Load every time
for file in changed_files:
    project = LookMLProject(Path("./lookml"))  # Slow!
    project.validate_view(file)
```

## Programmatic Usage

```python
from pathlib import Path
from lookerctl.utils.lookml_project import LookMLProject

# Load project
project = LookMLProject(Path("./lookml"))

# Validate all
errors = project.validate_all()
if errors:
    for error in errors:
        print(f"{error.file_path}:{error.line_number} - {error.message}")

# Get explore fields
fields = project.get_explore_fields("user_orders", include_hidden=False)
print(f"Found {len(fields['dimensions'])} dimensions")

# Check dependencies
deps = project.get_dependencies("users")
print(f"Users depends on: {deps}")
```

## Architecture

```
.lkml files
    ↓ parse (lkml library)
LookML AST
    ↓ extract
Views, Explores, Models
    ↓ build
NetworkX Dependency Graph
    ↓ validate
Errors with file/line numbers
```

## Summary

**Local validation is 66x faster** than API validation because:
- No API calls
- No git sync
- Works offline
- In-memory graph

Use it for rapid iteration, then use API validation for final check before merge.

For complete details, see the implementation in:
- `lookerctl/utils/lookml_types.py` - Type definitions
- `lookerctl/utils/lookml_parser.py` - LookML parser
- `lookerctl/utils/lookml_project.py` - Project graph

---

**Next**: [Query Testing](./QUERY_TESTING.md) | [AI Integration](./AI_INTEGRATION.md)
