# FlowForge MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server that exposes
FlowForge to MCP clients (Claude Desktop, Claude Code, any MCP host), so an
agent can inspect and **drive** workflows conversationally:

> "Create an incident workflow from this YAML, open an instance for the outage,
> and move it to Investigating."

It's a thin adapter over the FlowForge REST API — the engine, rules, auth, and
versioning all stay in FlowForge; this server just maps tools onto endpoints.

## Tools

| Tool | What it does |
|------|--------------|
| `list_workflows` | All workflow definitions |
| `get_workflow` | One workflow, summarised (states + named transitions) |
| `list_instances` | Instances, optionally filtered to a workflow |
| `get_instance` | Full detail: state, metadata, computed fields, available transitions |
| `search_instances` | Search by reference or workflow name |
| `get_topology` | Cross-workflow system map (nodes + edges) |
| `validate_workflow_yaml` | Dry-run a YAML definition (parse + lint, no write) |
| `create_workflow_from_yaml` | Create a workflow from the YAML DSL |
| `create_instance` | Start an instance, optionally with metadata |
| `fire_transition` | Advance an instance by transition name (rules/forms/hooks still apply) |

## Setup

```bash
cd mcp-server
python -m venv .venv && . .venv/bin/activate   # or your env of choice
pip install -r requirements.txt
cp .env.example .env    # then edit
```

Configure via environment (see `.env.example`):
- `FLOWFORGE_API_URL` — e.g. `http://localhost:8000/api`
- Either `FLOWFORGE_TOKEN` (a JWT) **or** `FLOWFORGE_EMAIL` + `FLOWFORGE_PASSWORD`
  (the server logs in and refreshes the JWT automatically).

The agent acts with the permissions of that account — scope it to a
least-privilege role for anything beyond local demoing.

## Register with a client

**Claude Desktop** (`claude_desktop_config.json`) or **Claude Code**
(`.mcp.json`):

```json
{
  "mcpServers": {
    "flowforge": {
      "command": "python",
      "args": ["/absolute/path/to/FlowForge/mcp-server/server.py"],
      "env": {
        "FLOWFORGE_API_URL": "http://localhost:8000/api",
        "FLOWFORGE_EMAIL": "admin@flowforge.dev",
        "FLOWFORGE_PASSWORD": "Admin1234!"
      }
    }
  }
}
```

Restart the client; the `flowforge` tools appear.

## Why this matters

FlowForge already turns "describe a process in YAML → click → working app" into
reality. This server turns it into "**describe a process to an agent → it's
built and running**" — the app-generation direction, with the agent driving the
same safe, rule-enforced engine a human would.

## Development

```bash
pytest test_tools.py       # unit tests (mocked API)
```
