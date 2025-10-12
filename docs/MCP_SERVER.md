# Looker MCP Server

This directory contains an MCP (Model Context Protocol) server that exposes Looker CLI functionality as tools for AI agents.

## What is MCP?

MCP is a protocol that allows AI assistants like Claude to interact with external tools and services. The Looker MCP server wraps the Looker CLI functionality, enabling AI agents to:

- Export LookML projects, dashboards, and looks
- Analyze content usage and find unused explores
- Manage git branches and workspaces
- Validate LookML projects
- Query explore schemas

## Available Tools

The MCP server exposes **20 tools** across 6 categories:

### Export Tools (4)
- **export_project** - Export LookML files from a specific project
- **export_all_projects** - Export LookML from all projects
- **export_dashboards** - Export user-defined dashboards as LookML
- **export_looks** - Export saved queries (looks) as JSON

### Analysis Tools (6)
- **analyze_usage** - Analyze explore and field usage across content
- **find_unused_content** - Find explores not used in dashboards or looks
- **get_explore_schema** - Get complete schema for an explore including all fields
- **list_explores** - List all available model.explore combinations
- **analyze_dependencies** - Build and analyze dependency graph for a LookML project
- **analyze_change_impact** - Analyze impact of changing/removing a view, explore, or field

### Session/Workspace Tools (5)
- **get_workspace** - Get current workspace (dev/production)
- **set_workspace** - Switch workspace
- **get_git_status** - Get git status for a project
- **checkout_branch** - Checkout a git branch
- **create_branch** - Create a new development branch

### Project Tools (2)
- **list_projects** - List all Looker projects
- **validate_project** - Validate a LookML project

### Query Testing Tools (1)
- **run_query** - Run a query against an explore and capture results

### Dependency Analysis Tools (2)
- **find_orphaned_views** - Find views not used by any explores
- **find_circular_deps** - Find circular dependencies in LookML project

## Usage

### Starting the Server

```bash
# Start with stdio transport (default, for Claude Desktop)
lookerctl mcp

# Start with SSE transport
lookerctl mcp --transport sse

# Start with streamable HTTP transport
lookerctl mcp --transport streamable-http
```

### Claude Desktop Integration

To use the Looker MCP server with Claude Desktop, add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "looker": {
      "command": "/absolute/path/tlookerctl",
      "args": ["mcp"],
      "env": {
        "LOOKERSDK_BASE_URL": "https://your-instance.looker.com",
        "LOOKERSDK_CLIENT_ID": "your-client-id",
        "LOOKERSDK_CLIENT_SECRET": "your-client-secret",
        "LOOKERSDK_API_VERSION": "4.0",
        "LOOKERSDK_VERIFY_SSL": "true"
      }
    }
  }
}
```

**Note:** Replace `/absolute/path/tlookerctl` with the actual absolute path to the script.

📋 **Template available**: See `claude_desktop_config.example.json` for a ready-to-use template.

On macOS, the config file is typically located at:
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

On Windows, it's typically at:
```
%APPDATA%\Claude\claude_desktop_config.json
```

On Linux, it's typically at:
```
~/.config/Claude/claude_desktop_config.json
```

### Environment Variables

The MCP server requires the same environment variables as the CLI:

- `LOOKERSDK_BASE_URL` - Your Looker instance URL
- `LOOKERSDK_CLIENT_ID` - API client ID
- `LOOKERSDK_CLIENT_SECRET` - API client secret
- `LOOKERSDK_API_VERSION` - API version (default: 4.0)
- `LOOKERSDK_VERIFY_SSL` - Verify SSL (default: true)

You can either:
1. Set these in your shell environment
2. Use a `.env` file and source it
3. Pass them via the `env` field in Claude Desktop config (recommended)

## Testing the Server

You can test that the server starts correctly:

```bash
# This should show the tools available
python -c "
from lookerctl.mcp_server import mcp
tools = mcp._tool_manager.list_tools()
print(f'Registered {len(tools)} tools:')
for tool in tools:
    print(f'  • {tool.name}')
"
```

## Example Prompts for Claude

Once configured in Claude Desktop, you can ask Claude things like:

### Export & Content
- "List all Looker projects"
- "Export the 'my_project' project to ./exports"
- "Export all dashboards to ./dashboards"
- "Export all looks with a limit of 50"

### Analysis & Discovery
- "Analyze usage across all dashboards and looks"
- "Find unused explores"
- "Get the schema for model.explore_name and save it to a file"
- "List all explores in the instance"
- "Show me which fields are available in the sales.orders explore"

### Dependencies & Impact
- "Analyze the dependencies in ./my_lookml_project"
- "Find orphaned views in ./my_lookml_project"
- "Check for circular dependencies in ./my_lookml_project"
- "What would be impacted if I change view.users in ./my_lookml_project?"

### Git & Branches
- "Create a new branch called 'feature-x' in project 'my_project'"
- "Get the git status for 'my_project'"
- "Checkout branch 'dev-branch' in 'my_project'"
- "What workspace am I currently in?"

### Validation & Testing
- "Validate the 'my_project' project"
- "Run a query on model.explore with fields users.count and users.city"
- "Test a query on sales.orders with fields order_items.count, products.category, limited to 100 rows"

## Architecture

The MCP server is implemented in `lookerctl/mcp_server.py` and:

1. Uses FastMCP to create the server
2. Wraps existing command functions from `lookerctl.commands.*`
3. Manages LookerClient instances automatically
4. Serializes results to JSON-compatible formats
5. Handles environment variable validation

Each tool:
- Takes simple parameters (strings, ints, etc.)
- Initializes a LookerClient context manager
- Calls the underlying command function
- Returns serialized results

## Extending the Server

To add new tools:

1. Add a new function in `lookerctl/mcp_server.py`
2. Decorate it with `@mcp.tool()`
3. Ensure it has proper type hints and a docstring
4. Handle LookerClient initialization and result serialization

Example:

```python
@mcp.tool()
def my_new_tool(param1: str, param2: int) -> dict[str, Any]:
    """
    Description of what this tool does.

    Args:
        param1: Description of param1
        param2: Description of param2

    Returns:
        Dictionary with results
    """
    _ensure_env_vars()

    with LookerClient() as client:
        # Call underlying function
        result = some_function(client, param1, param2)

    return _serialize_result(result)
```

## Troubleshooting

### Server won't start
- Check that all environment variables are set
- Verify Looker API credentials are correct
- Check network connectivity to Looker instance

### Claude Desktop doesn't see the server
- Verify the path to `looker.py` is absolute
- Check the Claude Desktop logs
- Ensure the script is executable (`chmod +x looker.py`)

### Tools return errors
- Check environment variables are properly configured
- Verify you have proper permissions in Looker
- Check the Looker API is accessible

## Development

The MCP server implementation follows these principles:

1. **Minimal wrapper overhead** - Tools directly wrap command functions
2. **Type safety** - All tools have proper type hints
3. **Self-documenting** - Docstrings are used by MCP for tool descriptions
4. **Error handling** - Proper error messages for common issues
5. **Stateless** - Each tool call gets a fresh LookerClient instance

## Resources

- [MCP Documentation](https://modelcontextprotocol.github.io/python-sdk/)
- [Claude Desktop MCP Guide](https://docs.anthropic.com/claude/docs/mcp)
- [Looker SDK Documentation](https://developers.looker.com/api/overview)
