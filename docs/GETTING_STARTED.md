# Getting Started with Looker CLI

This guide will help you set up and use the Looker CLI for the first time.

## Prerequisites

Before you begin, ensure you have:

1. **Python 3.10+** installed
2. **`uv` package manager** ([installation guide](https://github.com/astral-sh/uv))
3. **Looker API credentials** (client ID and secret)
4. **Access to a Looker instance**

## Installation

### Step 1: Clone Repository

```bash
cd /path/to/your/workspace
git clone <repository-url> looker_hub
cd looker_hub
```

### Step 2: Create Environment File

Create a `.env` file with your Looker credentials:

```bash
cat > .env << 'EOF'
export LOOKERSDK_BASE_URL=https://your-instance.looker.com:443
export LOOKERSDK_CLIENT_ID=your_client_id
export LOOKERSDK_CLIENT_SECRET=your_client_secret
export LOOKERSDK_VERIFY_SSL=true
export LOOKERSDK_API_VERSION=4.0
export LOOKERSDK_TIMEOUT=120
EOF
```

**Getting API Credentials**:
1. Log into your Looker instance
2. Go to Admin → Users → Your User
3. Click "Edit Keys"
4. Create a new API3 key
5. Copy the Client ID and Client Secret

### Step 3: Source Environment Variables

```bash
source .env
```

**Important**: You'll need to run `source .env` every time you open a new terminal session.

### Step 4: Install Dependencies

```bash
# Create virtual environment and install dependencies
uv venv
uv pip install -r requirements.txt

# Or if you have pyproject.toml
uv pip install -e .
```

### Step 5: Verify Installation

Test your connection to Looker:

```bash
lookerctl test
```

**Expected output**:
```
Configuration:
  Base URL: https://your-instance.looker.com:443
  API Version: 4.0
  Client ID: abc123...

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

If you see this, you're ready to go! 🎉

## First Steps

### 1. Explore Available Explores

Before you can query or test, you need to know what explores are available:

```bash
# List all explores
lookerctl analyze list-explores

# Save to file for reference
lookerctl analyze list-explores -o explores.json

# Search for specific explore
lookerctl analyze list-explores | grep -i "orders"
```

**AI Usage**: The `explores.json` file contains all model.explore combinations, perfect for AI systems to discover available explores programmatically.

### 2. Export Your First Project

Export LookML to your local filesystem:

```bash
# Export first available project
lookerctl export project --output-dir ./my-project

# Export specific project
lookerctl export project my-project-id --output-dir ./my-project

# Export everything
lookerctl export all --output-dir ./all-lookml
```

You'll now have local `.lkml` files you can edit directly.

### 3. Validate Locally (Fast!)

The killer feature - validate without API calls:

```bash
# Validate entire project (600ms!)
lookerctl validate static ./my-project

# Validate specific view
lookerctl validate static ./my-project --view users

# Validate specific explore
lookerctl validate static ./my-project --explore user_orders
```

This is **66x faster** than API validation!

### 4. Analyze Usage

Understand what's actually being used:

```bash
# Get usage summary
lookerctl analyze usage

# Save detailed usage data
lookerctl analyze usage --output usage.json

# Find unused explores
lookerctl analyze unused
```

**AI Usage**: The `usage.json` file contains complete usage mapping - which explores use which fields, where fields are referenced, etc.

### 5. Find a Working Explore for Testing

To run baselines and AB tests, you need an explore with accessible data:

```bash
# Find an explore
lookerctl analyze list-explores | grep -i "aws"
```

This command tests multiple explores and finds one that returns data successfully.

**Output example**:
```
Finding a working explore...

Testing analytics.billing... ✓ 10 rows returned

🎉 Found working explore: analytics.billing

Use this in baseline commands:
  lookerctl query-test baseline create analytics.billing \
    -q query.json -o baseline.json
```

### 6. Create Your First Baseline

Once you have a working explore:

```bash
# Step 1: Discover available fields
lookerctl analyze explore-fields analytics.billing \
  --output fields.json

# Step 2: Create query spec (query.json) using discovered fields
cat > query.json << 'JSON'
{
  "fields": ["billing_data.billingamount", "billing_data.count"],
  "filters": {"billing_data.starttime_date": "30 days"},
  "sorts": ["billing_data.count desc"],
  "limit": "10"
}
JSON

# Step 3: Test the query (dry-run)
lookerctl query-test baseline create analytics.billing \
  -q query.json --dry-run

# Step 4: Create baseline
lookerctl query-test baseline create analytics.billing \
  -q query.json -o baseline.json
```

## Common Workflows

### Workflow 1: Local Development

```bash
# 1. Sync Looker to your git branch
lookerctl session sync my-project

# 2. Export to local
lookerctl export project my-project -o ./local

# 3. Make changes to .lkml files
vim ./local/views/users.view.lkml

# 4. Validate locally (fast!)
lookerctl validate static ./local

# 5. Push to Looker dev branch
lookerctl export push my-project ./local

# 6. Commit to git
git add . && git commit -m "Updated users view"
```

### Workflow 2: AB Testing an Optimization

```bash
# 1. Create baseline BEFORE changes
lookerctl query-test baseline create model.explore \
  -q query.json -o before.json

# 2. Make your optimization changes

# 3. Compare AFTER changes
lookerctl query-test baseline compare model.explore \
  -b before.json

# 4. If passed, push changes
lookerctl export push my-project ./local
```

### Workflow 3: Understanding Usage

```bash
# 1. Export everything
lookerctl export all -o ./lookml

# 2. Analyze usage
lookerctl analyze usage -o usage.json

# 3. Find unused explores
lookerctl analyze unused

# 4. Build dependency graph
lookerctl deps build ./lookml -o deps.json

# 5. Check for orphaned views
lookerctl deps orphaned ./lookml
```

## Environment Setup Best Practices

### Shell Aliases

Add these to your `.bashrc` or `.zshrc`:

```bash
# Looker CLI aliases
alias looker="lookerctl"
alias looker-test="lookerctl test"
alias looker-validate="lookerctl validate static"
alias looker-usage="lookerctl analyze usage"

# Auto-source .env when entering directory
cd() {
  builtin cd "$@"
  if [ -f .env ]; then
    source .env
  fi
}
```

### Project Structure

Recommended directory structure:

```
looker_workspace/
├── .env                      # Credentials (gitignored!)
├── looker.py                 # CLI tool
├── lookerctl/               # CLI implementation
├── lookml_projects/          # Exported LookML
│   ├── project1/
│   └── project2/
├── baselines/                # Baseline snapshots
│   ├── explore1_before.json
│   └── explore1_after.json
├── golden_tests/             # Permanent tests
│   ├── test1.json
│   └── test2.json
├── queries/                  # Query specifications
│   └── explore1_query.json
└── analysis/                 # Usage and dependency data
    ├── usage.json
    └── deps.json
```

### Git Configuration

Add to `.gitignore`:

```gitignore
# Looker credentials
.env
*.secret

# Exported LookML (regenerate from source)
lookml_projects/
looker_export/

# Temporary baselines
baselines/*_temp.json
baselines/*_test.json

# Analysis outputs (regenerate as needed)
analysis/*.json
```

**Keep in git**:
- Golden tests (`golden_tests/`)
- Query specifications (`queries/`)
- Documentation
- The CLI tool itself

## Troubleshooting Setup

### Issue: Authentication Errors

**Error**: `Authentication failed` or `Invalid credentials`

**Solution**:
1. Verify you've sourced the .env file: `source .env`
2. Check credentials are correct
3. Verify API user has permissions
4. Test in Looker UI first

```bash
# Verify environment variables are set
echo $LOOKERSDK_BASE_URL
echo $LOOKERSDK_CLIENT_ID
```

### Issue: SSL Certificate Errors

**Error**: `SSL: CERTIFICATE_VERIFY_FAILED`

**Solution**:
```bash
# For self-signed certificates
export LOOKERSDK_VERIFY_SSL=false
```

**Warning**: Only use this in development/test environments!

### Issue: Import Errors

**Error**: `ModuleNotFoundError: No module named 'looker_sdk'`

**Solution**:
```bash
# Reinstall dependencies
uv pip install -r requirements.txt

# Or
uv pip install looker-sdk click rich pydantic gitpython lkml networkx python-dotenv
```

### Issue: Permission Errors

**Error**: `Permission denied: lookerctl`

**Solution**:
```bash
# Make script executable
chmod +x lookerctl

# Or run with python
python looker.py test
```

### Issue: Timeout Errors

**Error**: `Request timeout` or `Connection timeout`

**Solution**:
```bash
# Increase timeout in .env
export LOOKERSDK_TIMEOUT=300

# Source the file
source .env
```

## Next Steps

Now that you're set up, explore these topics:

1. **[Core Concepts](./CORE_CONCEPTS.md)** - Understand the tool's architecture
2. **[CLI Reference](./CLI_REFERENCE.md)** - Complete command reference
3. **[Workflows](./WORKFLOWS.md)** - Common patterns and use cases
4. **[Query Testing](./QUERY_TESTING.md)** - AB testing and baselines
5. **[Local Validation](./LOCAL_VALIDATION.md)** - Fast local validation
6. **[AI Integration](./AI_INTEGRATION.md)** - AI-driven workflows

## Getting Help

- **Troubleshooting**: See [Troubleshooting Guide](./TROUBLESHOOTING.md)
- **Examples**: Browse [Examples](./EXAMPLES.md)
- **Issues**: Report bugs via your team's issue tracker

## Quick Reference Card

```bash
# Setup
source .env
lookerctl test

# Core workflow
lookerctl export all -o ./lookml
lookerctl validate static ./lookml
lookerctl analyze usage -o usage.json
lookerctl export push my-project ./lookml/my-project

# Testing
lookerctl analyze list-explores | grep -i "orders"
lookerctl query-test baseline create model.explore -q query.json -o baseline.json
lookerctl query-test baseline compare model.explore -b baseline.json

# Analysis
lookerctl analyze list-explores
lookerctl analyze explore-fields model.explore
lookerctl deps build ./lookml
lookerctl deps impact view_name

# Session
lookerctl session sync
lookerctl session workspace dev
```

---

**Congratulations! You're ready to use the Looker CLI.** 🎉

Start with `lookerctl test` and explore from there!
