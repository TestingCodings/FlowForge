"""
FlowForge MCP server.

Exposes FlowForge to MCP clients (Claude Desktop, Claude Code, any MCP host)
as a set of tools, so an agent can inspect and drive workflows conversationally:
"create an incident workflow from this YAML, open an instance, and move it to
Investigating." It's a thin adapter over the FlowForge REST API.

Run:  python server.py            (stdio transport, for Claude Desktop/Code)
Env:  FLOWFORGE_API_URL, and either FLOWFORGE_TOKEN or
      FLOWFORGE_EMAIL + FLOWFORGE_PASSWORD.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from client import FlowForgeClient, FlowForgeError

mcp = FastMCP("flowforge")
_client: FlowForgeClient | None = None


def client() -> FlowForgeClient:
    global _client
    if _client is None:
        _client = FlowForgeClient()
    return _client


def _summarise_workflow(wf: dict) -> dict:
    return {
        "id": wf["id"], "name": wf["name"], "version": wf.get("version"),
        "shell": (wf.get("ui_schema") or {}).get("shell", "list"),
        "states": [s["name"] for s in wf.get("states", [])],
        "transitions": [
            {"name": t["name"], "from": _state_name(wf, t["from_state"]), "to": _state_name(wf, t["to_state"])}
            for t in wf.get("transitions", [])
        ],
    }


def _state_name(wf: dict, state_id: str) -> str:
    for s in wf.get("states", []):
        if s["id"] == state_id:
            return s["name"]
    return state_id


# ── read ──

@mcp.tool()
def list_workflows() -> list[dict]:
    """List all workflow definitions (id, name, version, shell, state count)."""
    c = client()
    return [
        {"id": w["id"], "name": w["name"], "version": w.get("version"),
         "states": len(w.get("states", [])), "active": w.get("is_active")}
        for w in c._list(c.get("/workflows/"))
    ]


@mcp.tool()
def get_workflow(workflow_id: str) -> dict:
    """Get one workflow definition, summarised: states and transitions with names."""
    return _summarise_workflow(client().get(f"/workflows/{workflow_id}/"))


@mcp.tool()
def list_instances(workflow_id: str = "") -> list[dict]:
    """List instances, optionally filtered to one workflow. Returns reference, state, workflow."""
    c = client()
    path = f"/instances/?workflow_definition={workflow_id}" if workflow_id else "/instances/"
    return [
        {"id": i["id"], "reference": i["reference_number"],
         "workflow": i["workflow_definition_name"], "state": i["current_state_name"],
         "completed": i["completed_at"] is not None}
        for i in c._list(c.get(path))
    ]


@mcp.tool()
def get_instance(instance_id: str) -> dict:
    """Full detail for one instance: state, metadata, computed fields, available transitions."""
    c = client()
    inst = c.get(f"/instances/{instance_id}/")
    wf = c.get(f"/workflows/{inst['workflow_definition']}/")
    available = [
        {"id": t["id"], "name": t["name"]}
        for t in wf.get("transitions", [])
        if t["from_state"] == inst["current_state"]
    ]
    return {
        "id": inst["id"], "reference": inst["reference_number"],
        "workflow": inst["workflow_definition_name"], "state": inst["current_state_name"],
        "metadata": inst.get("metadata_json", {}), "computed": inst.get("computed", {}),
        "completed": inst["completed_at"] is not None,
        "available_transitions": available,
    }


@mcp.tool()
def search_instances(query: str) -> list[dict]:
    """Search instances by reference number or workflow name (min 2 chars)."""
    return client().get(f"/instances/search/?q={query}")


@mcp.tool()
def get_topology(root: str = "", depth: int = 2) -> dict:
    """Cross-workflow system map: nodes (instances) and edges (relationships/containment).
    Optionally root at one instance id and limit BFS depth."""
    qs = f"?root={root}&depth={depth}" if root else ""
    return client().get(f"/topology/{qs}")


# ── write ──

@mcp.tool()
def validate_workflow_yaml(yaml_text: str) -> dict:
    """Validate a workflow YAML definition without creating it. Returns the parsed
    graph + any lint warnings, or a line-referenced error."""
    try:
        return client().post("/workflows/compose-yaml/?dry_run=true", json={"text": yaml_text})
    except FlowForgeError as exc:
        return {"error": str(exc)}


@mcp.tool()
def create_workflow_from_yaml(yaml_text: str) -> dict:
    """Create a workflow from a YAML definition (the FlowForge DSL). Returns the
    created workflow summary, or a line-referenced error."""
    try:
        wf = client().post("/workflows/compose-yaml/", json={"text": yaml_text})
        return _summarise_workflow(wf)
    except FlowForgeError as exc:
        return {"error": str(exc)}


@mcp.tool()
def create_instance(workflow_id: str, metadata: dict | None = None) -> dict:
    """Create a new instance of a workflow, optionally with initial metadata."""
    inst = client().post("/instances/", json={
        "workflow_definition": workflow_id, "metadata_json": metadata or {},
    })
    return {"id": inst["id"], "reference": inst["reference_number"], "state": inst["current_state_name"]}


@mcp.tool()
def fire_transition(instance_id: str, transition_name: str) -> dict:
    """Advance an instance by firing the named transition available from its current
    state. Rules, approvals, required forms, and before-hooks still apply — a blocked
    transition returns the reason."""
    c = client()
    inst = c.get(f"/instances/{instance_id}/")
    wf = c.get(f"/workflows/{inst['workflow_definition']}/")
    match = next(
        (t for t in wf.get("transitions", [])
         if t["from_state"] == inst["current_state"] and t["name"].lower() == transition_name.lower()),
        None,
    )
    if match is None:
        avail = [t["name"] for t in wf.get("transitions", []) if t["from_state"] == inst["current_state"]]
        return {"error": f"No transition '{transition_name}' from '{inst['current_state_name']}'. Available: {avail}"}
    try:
        c.post(f"/instances/{instance_id}/transition/", json={"transition_id": match["id"]})
    except FlowForgeError as exc:
        return {"error": str(exc)}
    updated = c.get(f"/instances/{instance_id}/")
    return {"reference": updated["reference_number"], "state": updated["current_state_name"],
            "completed": updated["completed_at"] is not None}


if __name__ == "__main__":
    mcp.run()  # stdio transport
