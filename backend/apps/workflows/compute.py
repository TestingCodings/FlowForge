"""
Computed fields (docs/METAMODEL.md §2).

Derived, read-only values defined per workflow in `ui_schema.computed`. They
are resolved at read time (never stored, so they can't drift) and injected
into the data the rules engine sees, so a rule or a card can reference a
rollup like `total_cost` or a derived `risk` band.

v1 expressions (single pass — a computed field may not reference another):
    {"expr": "sum|min|max|avg|count", "over": "children", "field": "metadata.<k>"}
    {"expr": "sum|min|max|avg|count", "over": "relationships", "field": "metadata.<k>",
     "rel_type": "<optional filter>"}
    {"expr": "age_days", "from": "created_at" | "metadata.<k>"}
    {"expr": "if", "cond": {"field","operator"/"op","value"}, "then": ..., "else": ...}
"""
from __future__ import annotations

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .rules import _compare

AGG = ("sum", "min", "max", "avg", "count")
VALID_EXPRS = (*AGG, "age_days", "if")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _child_numbers(instance, field: str) -> list[float]:
    key = field.split("metadata.", 1)[1] if field.startswith("metadata.") else field
    out = []
    for child in instance.children.all():
        n = _num((child.metadata_json or {}).get(key))
        if n is not None:
            out.append(n)
    return out


def _relationship_instances(instance, rel_type=None):
    """Return peer instances linked to this instance via relationships (both directions).

    Uses prefetch_related cache when available, so list views with
    ?include=computed don't issue per-instance queries.
    """
    peers = []
    for rel in instance.outgoing_relationships.all():
        if rel_type is None or rel.rel_type == rel_type:
            peers.append(rel.to_instance)
    for rel in instance.incoming_relationships.all():
        if rel_type is None or rel.rel_type == rel_type:
            peers.append(rel.from_instance)
    return peers


def _rel_numbers(instance, field: str, rel_type=None) -> list[float]:
    key = field.split("metadata.", 1)[1] if field.startswith("metadata.") else field
    out = []
    for peer in _relationship_instances(instance, rel_type):
        n = _num((peer.metadata_json or {}).get(key))
        if n is not None:
            out.append(n)
    return out


def _evaluate(instance, spec: dict):
    expr = spec.get("expr")

    if expr == "count" and spec.get("over") == "children":
        return instance.children.count()

    if expr in ("sum", "min", "max", "avg") and spec.get("over") == "children":
        vals = _child_numbers(instance, spec.get("field", ""))
        if expr == "sum":
            return sum(vals)
        if not vals:
            return None
        if expr == "min":
            return min(vals)
        if expr == "max":
            return max(vals)
        return round(sum(vals) / len(vals), 4)

    if expr == "count" and spec.get("over") == "relationships":
        return len(_relationship_instances(instance, spec.get("rel_type")))

    if expr in ("sum", "min", "max", "avg") and spec.get("over") == "relationships":
        rel_type = spec.get("rel_type")
        vals = _rel_numbers(instance, spec.get("field", ""), rel_type)
        if expr == "sum":
            return sum(vals)
        if not vals:
            return None
        if expr == "min":
            return min(vals)
        if expr == "max":
            return max(vals)
        return round(sum(vals) / len(vals), 4)

    if expr == "age_days":
        src = spec.get("from", "created_at")
        if src == "created_at":
            dt = instance.created_at
        else:
            key = src.split("metadata.", 1)[1] if src.startswith("metadata.") else src
            raw = (instance.metadata_json or {}).get(key)
            dt = parse_datetime(raw) if isinstance(raw, str) else None
        if dt is None:
            return None
        return round((timezone.now() - dt).total_seconds() / 86400, 1)

    if expr == "if":
        cond = spec.get("cond", {}) or {}
        lhs = (instance.metadata_json or {}).get(cond.get("field"))
        op = cond.get("operator") or cond.get("op")
        return spec.get("then") if _compare(lhs, op, cond.get("value")) else spec.get("else")

    return None


def compute_fields(instance) -> dict:
    """Return {name: value} for every computed field on this instance's workflow."""
    schema = (getattr(instance.workflow_definition, "ui_schema", None) or {}).get("computed") or {}
    result = {}
    for name, spec in schema.items():
        if not isinstance(spec, dict):
            continue
        try:
            result[name] = _evaluate(instance, spec)
        except Exception:
            result[name] = None
    return result
