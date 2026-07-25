"""
Cross-instance topology (VISION meta-model: the system map).

A read-only view over data that already exists — InstanceRelationship
(directional typed links) and parent containment — assembled into a graph of
real instances and how they connect, across workflow boundaries.

Unlike the state diagram (one workflow definition's states), this renders
many instances (real assets) and the edges between them. No new storage.
"""
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import InstanceRelationship, WorkflowInstance

MAX_NODES = 200  # keep a large estate legible + the response bounded


def _instance_title(instance):
    """Resolve the instance's display title from its workflow's title_field, if any."""
    field = (instance.workflow_definition.ui_schema or {}).get("title_field")
    if not field:
        return None
    value = (instance.metadata_json or {}).get(field)
    return None if value in (None, "") else str(value)


def _node(instance):
    return {
        "id": str(instance.id),
        "reference": instance.reference_number,
        "workflow": instance.workflow_definition.name,
        "workflow_id": str(instance.workflow_definition_id),
        "state": instance.current_state.name if instance.current_state_id else None,
        "title": _instance_title(instance),
        "completed": instance.completed_at is not None,
    }


class TopologyView(APIView):
    """
    GET /api/topology/

    Query params (all optional):
      root        instance id to start from; omitted = whole estate (capped)
      depth       BFS hops from root (default 2, ignored without root)
      rel_types   comma-separated relationship types to include
      workflow    workflow_definition id to filter nodes by

    Returns {nodes, edges, root, truncated}. Edges are relationship links
    (kind="relationship") and parent→child containment (kind="containment").
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        root_id = request.query_params.get("root")
        try:
            depth = int(request.query_params.get("depth", 2))
        except (TypeError, ValueError):
            depth = 2
        rel_types = [t for t in (request.query_params.get("rel_types", "").split(",")) if t]
        workflow_id = request.query_params.get("workflow")

        base = WorkflowInstance.objects.select_related(
            "workflow_definition", "current_state"
        )

        if root_id:
            nodes, edges, truncated = self._bfs(root_id, depth, rel_types)
        else:
            nodes, edges, truncated = self._whole_estate(base, rel_types, workflow_id)

        return Response({
            "root": root_id,
            "nodes": list(nodes.values()),
            "edges": edges,
            "truncated": truncated,
        })

    # ── Rooted: breadth-first out from one instance ──
    def _bfs(self, root_id, depth, rel_types):
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        seen_edges: set[str] = set()
        truncated = False

        try:
            root = WorkflowInstance.objects.select_related(
                "workflow_definition", "current_state"
            ).get(id=root_id)
        except (WorkflowInstance.DoesNotExist, ValueError):
            return nodes, edges, truncated

        frontier = [root]
        nodes[str(root.id)] = _node(root)

        for _ in range(max(0, depth)):
            if not frontier:
                break
            next_frontier = []
            for inst in frontier:
                neighbours = self._neighbours(inst, rel_types)
                for edge, other in neighbours:
                    if edge["id"] not in seen_edges:
                        seen_edges.add(edge["id"])
                        edges.append(edge)
                    if str(other.id) not in nodes:
                        if len(nodes) >= MAX_NODES:
                            truncated = True
                            continue
                        nodes[str(other.id)] = _node(other)
                        next_frontier.append(other)
            frontier = next_frontier

        return nodes, edges, truncated

    def _neighbours(self, inst, rel_types):
        """Return [(edge, other_instance)] for one instance: relationships + containment."""
        out = []

        rels = InstanceRelationship.objects.filter(
            Q(from_instance=inst) | Q(to_instance=inst)
        ).select_related(
            "from_instance__workflow_definition", "from_instance__current_state",
            "to_instance__workflow_definition", "to_instance__current_state",
        )
        if rel_types:
            rels = rels.filter(rel_type__in=rel_types)
        for rel in rels:
            other = rel.to_instance if rel.from_instance_id == inst.id else rel.from_instance
            out.append((
                {
                    "id": f"rel-{rel.id}",
                    "source": str(rel.from_instance_id),
                    "target": str(rel.to_instance_id),
                    "type": rel.rel_type,
                    "kind": "relationship",
                },
                other,
            ))

        # Containment: parent and children (skipped when rel_types filter is on,
        # since containment is not a rel_type).
        if not rel_types:
            if inst.parent_id:
                parent = WorkflowInstance.objects.select_related(
                    "workflow_definition", "current_state"
                ).get(id=inst.parent_id)
                out.append((self._containment_edge(parent.id, inst.id), parent))
            for child in inst.children.select_related("workflow_definition", "current_state").all():
                out.append((self._containment_edge(inst.id, child.id), child))

        return out

    @staticmethod
    def _containment_edge(parent_id, child_id):
        return {
            "id": f"parent-{child_id}",
            "source": str(parent_id),
            "target": str(child_id),
            "type": "contains",
            "kind": "containment",
        }

    # ── Unrooted: the whole estate, capped ──
    def _whole_estate(self, base, rel_types, workflow_id):
        qs = base
        if workflow_id:
            qs = qs.filter(workflow_definition_id=workflow_id)
        instances = list(qs[:MAX_NODES])
        truncated = qs.count() > MAX_NODES
        nodes = {str(i.id): _node(i) for i in instances}
        node_ids = set(nodes)

        edges = []
        rels = InstanceRelationship.objects.all()
        if rel_types:
            rels = rels.filter(rel_type__in=rel_types)
        for rel in rels.values("id", "from_instance_id", "to_instance_id", "rel_type"):
            s, t = str(rel["from_instance_id"]), str(rel["to_instance_id"])
            if s in node_ids and t in node_ids:
                edges.append({
                    "id": f"rel-{rel['id']}", "source": s, "target": t,
                    "type": rel["rel_type"], "kind": "relationship",
                })

        if not rel_types:
            for inst in instances:
                if inst.parent_id and str(inst.parent_id) in node_ids:
                    edges.append(self._containment_edge(inst.parent_id, inst.id))

        return nodes, edges, truncated
