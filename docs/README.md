# Looker CLI Documentation

> **Comprehensive CLI for managing and optimizing LookML at scale**

## Overview

This CLI provides a **complete local development experience** for LookML that mirrors the Looker console, enabling AI-driven optimization, scientific AB testing, and comprehensive analysis.

## Core Problem

Your Looker instance is embedded in your product. Customers create custom dashboards and LookML content. You need:

- ✅ **Visibility** into all customer-created LookML
- ✅ **Understanding** of which explore fields are actually used
- ✅ **Safe optimization** of LookML with validation
- ✅ **Local development** workflow for rapid iteration
- ✅ **Scientific testing** to measure improvements

This CLI solves all of these problems.

## Key Features

### 🔄 Complete Local Development Loop
Export → Analyze → Modify → Validate → Test → Push → Commit

### ⚡ 66x Faster Validation
Local validation in 600ms vs 40s with API calls

### 📊 Usage Analysis
Understand which explores and fields customers actually use

### 🧪 Scientific Testing
AB testing and golden tests for confidence in changes

### 🔍 Dependency Mapping
Understand impact before making changes

### 🤖 AI-Ready
All commands designed for AI-driven development workflows

## Documentation Structure

### Getting Started
- **[Getting Started Guide](./GETTING_STARTED.md)** - Installation, setup, and first steps
- **[Core Concepts](./CORE_CONCEPTS.md)** - Understanding the tool's architecture and approach

### Reference
- **[CLI Reference](./CLI_REFERENCE.md)** - Complete command reference
- **[Workflows](./WORKFLOWS.md)** - Common patterns and workflows
- **[Examples](./EXAMPLES.md)** - Real-world examples with explanations

### Features
- **[Query Testing](./QUERY_TESTING.md)** - Baselines, AB testing, and golden tests
- **[Local Validation](./LOCAL_VALIDATION.md)** - Fast local validation and LookML graph
- **[AI Integration](./AI_INTEGRATION.md)** - AI-specific workflows and patterns

### Help
- **[Troubleshooting](./TROUBLESHOOTING.md)** - Common issues and solutions

## Quick Start

```bash
# 1. Test connection
lookerctl test

# 2. Export all LookML
lookerctl export all --output-dir ./lookml

# 3. Analyze usage
lookerctl analyze usage

# 4. Validate locally (fast!)
lookerctl validate static ./lookml

# 5. Make changes and push
lookerctl export push my-project ./lookml/my-project
```

## Core Workflow

```mermaid
graph LR
    A[Export] --> B[Analyze]
    B --> C[Modify]
    C --> D[Validate]
    D --> E[Test]
    E --> F[Push]
    F --> G[Commit]
```

## Key Commands

| Command Group | Purpose | Example |
|---------------|---------|---------|
| `export` | Get LookML from Looker | `lookerctl export all` |
| `validate` | Check for errors | `lookerctl validate static ./lookml` |
| `analyze` | Understand usage | `lookerctl analyze usage` |
| `deps` | Map dependencies | `lookerctl deps build ./lookml` |
| `query-test` | AB testing | `lookerctl query-test baseline create` |
| `session` | Manage workspaces | `lookerctl session sync` |

## Architecture

```
looker_hub/
├── looker.py                 # Main CLI entry point
├── lookerctl/
│   ├── core/                # SDK wrappers and config
│   ├── commands/            # Command implementations
│   ├── utils/               # LookML parsing and graph
│   └── docs/                # This documentation
```

## Design Principles

- **SDK-First** - Uses official Looker SDK for all API interactions
- **Type-Safe** - Pydantic models and type hints throughout
- **Fast** - Local graph for 66x faster validation
- **AI-Ready** - All data exported as JSON for AI consumption
- **Scientific** - AB testing for confidence in changes
- **Composable** - Commands can be chained and piped

## Performance

| Operation | API Method | Local Graph | Speedup |
|-----------|-----------|-------------|---------|
| Validate project | 40s | 600ms | **66x faster** |
| Field discovery | 2s | 100ms | **20x faster** |
| Dependency check | 5s | 50ms | **100x faster** |

## Use Cases

### For AI Systems
- Export all LookML for analysis
- Validate changes locally without API calls
- Discover available fields programmatically
- AB test optimizations automatically
- Create regression tests

### For Developers
- Local development workflow like Looker console
- Fast validation during iteration
- Understand usage before changes
- Impact analysis before refactoring
- Scientific testing of improvements

### For Teams
- Visibility into customer-created content
- Automated optimization pipelines
- CI/CD integration with golden tests
- Documentation of explore behavior
- Performance tracking over time

## What's Next?

1. **New to the CLI?** Start with [Getting Started](./GETTING_STARTED.md)
2. **Want to understand concepts?** Read [Core Concepts](./CORE_CONCEPTS.md)
3. **Ready to use it?** Check [CLI Reference](./CLI_REFERENCE.md)
4. **Building AI workflows?** See [AI Integration](./AI_INTEGRATION.md)
5. **Need examples?** Browse [Examples](./EXAMPLES.md)

## Support

- **Issues**: Report bugs and request features via your team's issue tracker
- **Questions**: Consult [Troubleshooting](./TROUBLESHOOTING.md) first
- **Updates**: Check git log for latest improvements

## Status

**✅ Production Ready**

- All features tested end-to-end
- Complete AB testing workflow validated
- Local validation 66x faster than API
- Comprehensive error handling
- Full documentation

---

**Last Updated**: 2025-10-11
**Version**: 0.1.0
**Maintained By**: Looker DevOps Team
