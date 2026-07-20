"""
Text-first workflow authoring: YAML DSL → portability bundle.

The DSL is a compact, human-writable format that compiles to the same
bundle dict produced by portability.export_workflow, so creation goes
through the existing (validated, atomic) bundle importer. See
docs/BUILDER.md Part 3 for the format rationale.

Example:

    workflow: Expense Approval
    prefix: EXP
    description: Simple expense approval

    states:
      - name: Submitted          # first state is initial by default
        sla_hours: 24
      - name: Manager Review
        role: approver
        form:
          fields:
            - {key: amount, type: number, label: Amount, required: true}
      - name: Approved
        terminal: true

    transitions:
      - Submitted -> Manager Review: Submit
      - Manager Review -> Approved:
          name: Approve
          requires_approval: true
          rules:
            - if: {field: amount, op: gt, value: 5000}
              then: {block_transition: true}

Shorthand: a plain string in `states` is a state with just a name; a
`A -> B: Name` mapping in `transitions` is a transition with defaults.
"""

import re

import yaml

from .portability import BUNDLE_VERSION

TRANSITION_KEY_RE = re.compile(r"^\s*(.+?)\s*->\s*(.+?)\s*$")

# DSL condition op → engine operator (engine names pass through unchanged)
_OP_ALIASES = {
    "op": "operator",
}
_VALID_OPERATORS = {
    "eq", "ne", "gt", "gte", "lt", "lte",
    "contains", "starts_with", "is_true", "is_false", "and", "or",
}


class DslError(ValueError):
    """Parse/validation failure. `errors` is a list of line-annotated strings."""

    def __init__(self, errors):
        self.errors = errors if isinstance(errors, list) else [errors]
        super().__init__("; ".join(self.errors))


class _LineLoader(yaml.SafeLoader):
    """SafeLoader that records the source line of every mapping."""


def _construct_mapping(loader, node, deep=False):
    mapping = yaml.SafeLoader.construct_mapping(loader, node, deep=deep)
    mapping["__line__"] = node.start_mark.line + 1
    return mapping


_LineLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _line(obj, fallback=None):
    if isinstance(obj, dict):
        return obj.get("__line__", fallback)
    return fallback


def _strip_lines(obj):
    """Recursively remove __line__ markers before handing data onward."""
    if isinstance(obj, dict):
        return {k: _strip_lines(v) for k, v in obj.items() if k != "__line__"}
    if isinstance(obj, list):
        return [_strip_lines(v) for v in obj]
    return obj


def _normalise_condition(cond, errors, line):
    """Accept engine-format or {field, op, value} shorthand; recurse into and/or."""
    if not isinstance(cond, dict):
        errors.append(f"line {line}: rule condition must be a mapping")
        return {}
    cond = {(_OP_ALIASES.get(k, k)): v for k, v in cond.items() if k != "__line__"}
    op = cond.get("operator")
    if op in {"and", "or"}:
        cond["conditions"] = [
            _normalise_condition(c, errors, _line(c, line))
            for c in cond.get("conditions", [])
        ]
    elif op not in _VALID_OPERATORS:
        errors.append(f"line {line}: unknown rule operator '{op}'")
    return cond


def parse_dsl(text: str) -> dict:
    """Compile DSL text into a portability bundle dict.

    Raises DslError with line-annotated messages on any problem.
    """
    try:
        doc = yaml.load(text, Loader=_LineLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = f"line {mark.line + 1}: " if mark else ""
        problem = getattr(exc, "problem", None) or str(exc)
        raise DslError(f"{line}invalid YAML — {problem}")

    if not isinstance(doc, dict):
        raise DslError("line 1: document must be a mapping (start with 'workflow: <name>')")

    errors: list[str] = []

    name = doc.get("workflow")
    if not name or not isinstance(name, str):
        errors.append(f"line {_line(doc, 1)}: 'workflow: <name>' is required")

    raw_states = doc.get("states") or []
    if not isinstance(raw_states, list) or not raw_states:
        errors.append(f"line {_line(doc, 1)}: at least one entry under 'states:' is required")
        raw_states = []

    states, forms = [], []
    state_names: list[str] = []
    explicit_initial = False
    for i, raw in enumerate(raw_states):
        if isinstance(raw, str):
            raw = {"name": raw}
        if not isinstance(raw, dict) or not raw.get("name"):
            errors.append(f"line {_line(raw, '?')}: each state needs a 'name'")
            continue
        line = _line(raw)
        sname = str(raw["name"]).strip()
        if sname in state_names:
            errors.append(f"line {line}: duplicate state name '{sname}'")
            continue
        state_names.append(sname)

        is_initial = bool(raw.get("initial", False))
        explicit_initial = explicit_initial or is_initial
        sla_hours = raw.get("sla_hours")
        if sla_hours is not None and (not isinstance(sla_hours, (int, float)) or sla_hours <= 0):
            errors.append(f"line {line}: sla_hours must be a positive number")
            sla_hours = None

        task_config = {}
        if raw.get("role"):
            task_config["default_role"] = str(raw["role"])
        if raw.get("no_task"):
            task_config["requires_task"] = False

        states.append({
            "name": sname,
            "display_name": str(raw.get("display_name", sname)),
            "is_initial": is_initial,
            "is_terminal": bool(raw.get("terminal", False)),
            "position_order": i + 1,
            "sla_config": {"sla_hours": sla_hours} if sla_hours else {},
            "task_config": task_config,
        })

        form = raw.get("form")
        if form is not None:
            if not isinstance(form, dict) or not isinstance(form.get("fields"), list):
                errors.append(f"line {line}: form must be a mapping with a 'fields' list")
            else:
                forms.append({
                    "state": sname,
                    "name": str(form.get("name", f"{sname} Form")),
                    "schema": _strip_lines({k: v for k, v in form.items() if k not in {"name", "__line__"}}),
                    "version": 1,
                })

    # Default: first state is initial unless one was marked explicitly
    if states and not explicit_initial:
        states[0]["is_initial"] = True
    initials = [s for s in states if s["is_initial"]]
    if len(initials) > 1:
        errors.append("exactly one state may be marked 'initial: true'")

    raw_transitions = doc.get("transitions") or []
    if not isinstance(raw_transitions, list):
        errors.append(f"line {_line(doc, 1)}: 'transitions:' must be a list")
        raw_transitions = []

    transitions, rules = [], []
    seen_transition_names: set[str] = set()
    for raw in raw_transitions:
        if not isinstance(raw, dict):
            errors.append(f"transition entries must be '<From> -> <To>: <Name>' mappings, got: {raw!r}")
            continue
        line = _line(raw)
        arrow_keys = [k for k in raw if isinstance(k, str) and TRANSITION_KEY_RE.match(k)]
        if not arrow_keys:
            errors.append(f"line {line}: transition needs an '<From> -> <To>' key")
            continue
        key = arrow_keys[0]
        from_state, to_state = TRANSITION_KEY_RE.match(key).groups()
        value = raw[key]

        if isinstance(value, str):
            spec = {"name": value}
        elif isinstance(value, dict):
            spec = value
        elif value is None:
            spec = {}
        else:
            errors.append(f"line {line}: transition value must be a name or a mapping")
            continue
        line = _line(spec, line)

        for endpoint, label in ((from_state, "from"), (to_state, "to")):
            if endpoint not in state_names:
                hint = _closest(endpoint, state_names)
                suffix = f" — did you mean '{hint}'?" if hint else ""
                errors.append(f"line {line}: transition references unknown state '{endpoint}'{suffix}")

        tname = str(spec.get("name", f"{from_state} → {to_state}"))
        if tname in seen_transition_names:
            errors.append(f"line {line}: duplicate transition name '{tname}'")
        seen_transition_names.add(tname)

        transitions.append({
            "name": tname,
            "display_name": str(spec.get("display_name", "")),
            "from_state": from_state,
            "to_state": to_state,
            "requires_approval": bool(spec.get("requires_approval", False)),
        })

        for rule in spec.get("rules", []) or []:
            if not isinstance(rule, dict) or "if" not in rule:
                errors.append(f"line {_line(rule, line)}: each rule needs 'if:' and 'then:'")
                continue
            rline = _line(rule, line)
            condition = _normalise_condition(rule["if"], errors, rline)
            action = rule.get("then")
            if not isinstance(action, dict):
                errors.append(f"line {rline}: rule 'then:' must be a mapping")
                continue
            rules.append({
                "transition": tname,
                "condition": _strip_lines(condition),
                "action": _strip_lines(action),
                "priority": int(rule.get("priority", 100)),
            })

    if errors:
        raise DslError(errors)

    prefix = str(doc.get("prefix", "WFF")).upper()[:10]
    return {
        "bundle_version": BUNDLE_VERSION,
        "kind": "flowforge.workflow",
        "workflow": {
            "name": str(name).strip(),
            "description": str(doc.get("description", "")),
            "reference_prefix": prefix,
            "version": 1,
            "is_active": bool(doc.get("active", True)),
            "ui_schema": _strip_lines(doc.get("ui", {}) or {}),
        },
        "states": states,
        "transitions": transitions,
        "rules": rules,
        "forms": forms,
    }


def _closest(needle: str, haystack: list[str]) -> str | None:
    """Did-you-mean suggestion for a misspelled state name."""
    import difflib

    matches = difflib.get_close_matches(needle, haystack, n=1, cutoff=0.6)
    return matches[0] if matches else None


def lint_bundle(bundle: dict) -> list[str]:
    """Graph sanity warnings (non-blocking) for a parsed bundle."""
    warnings = []
    states = bundle.get("states", [])
    transitions = bundle.get("transitions", [])
    by_name = {s["name"]: s for s in states}

    outgoing: dict[str, list[str]] = {s["name"]: [] for s in states}
    for t in transitions:
        outgoing.setdefault(t["from_state"], []).append(t["to_state"])

    # Reachability from the initial state
    initial = next((s["name"] for s in states if s.get("is_initial")), None)
    if initial:
        seen = set()
        stack = [initial]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(outgoing.get(cur, []))
        for s in states:
            if s["name"] not in seen:
                warnings.append(f"state '{s['name']}' is unreachable from the start state")

    for s in states:
        outs = outgoing.get(s["name"], [])
        if s.get("is_terminal") and outs:
            warnings.append(f"terminal state '{s['name']}' has outgoing transitions")
        if not s.get("is_terminal") and not outs:
            warnings.append(f"state '{s['name']}' is a dead end (non-terminal with no way out)")
        if s.get("is_terminal") and (s.get("sla_config") or {}).get("sla_hours"):
            warnings.append(f"terminal state '{s['name']}' has an SLA (it will never be met or breached)")

    if not any(s.get("is_terminal") for s in states):
        warnings.append("workflow has no terminal state — instances can never complete")

    return warnings


def export_dsl(bundle: dict) -> str:
    """Render a bundle back to DSL text (round-trip for 'View as YAML')."""
    wf = bundle.get("workflow", {})
    lines = [f"workflow: {wf.get('name', '')}"]
    if wf.get("reference_prefix"):
        lines.append(f"prefix: {wf['reference_prefix']}")
    if wf.get("description"):
        lines.append(f"description: {wf['description']}")
    if not wf.get("is_active", True):
        lines.append("active: false")

    forms_by_state = {}
    for f in bundle.get("forms", []):
        forms_by_state.setdefault(f["state"], f)

    lines.append("")
    lines.append("states:")
    states = bundle.get("states", [])
    first_initial = bool(states) and states[0].get("is_initial")
    for i, s in enumerate(states):
        lines.append(f"  - name: {s['name']}")
        if s.get("is_initial") and not (i == 0 and first_initial):
            lines.append("    initial: true")
        if s.get("is_terminal"):
            lines.append("    terminal: true")
        sla = (s.get("sla_config") or {}).get("sla_hours")
        if sla:
            lines.append(f"    sla_hours: {sla}")
        role = (s.get("task_config") or {}).get("default_role")
        if role:
            lines.append(f"    role: {role}")
        if (s.get("task_config") or {}).get("requires_task") is False:
            lines.append("    no_task: true")
        form = forms_by_state.get(s["name"])
        if form:
            form_yaml = yaml.safe_dump(
                {"form": {"name": form["name"], **(form.get("schema") or {})}},
                default_flow_style=False, sort_keys=False, allow_unicode=True,
            )
            lines.extend("    " + ln for ln in form_yaml.splitlines())

    rules_by_transition: dict[str, list] = {}
    for r in bundle.get("rules", []):
        if r.get("transition"):
            rules_by_transition.setdefault(r["transition"], []).append(r)

    lines.append("")
    lines.append("transitions:")
    for t in bundle.get("transitions", []):
        key = f"{t['from_state']} -> {t['to_state']}"
        t_rules = rules_by_transition.get(t["name"], [])
        if not t.get("requires_approval") and not t_rules:
            lines.append(f"  - {key}: {t['name']}")
            continue
        lines.append(f"  - {key}:")
        lines.append(f"      name: {t['name']}")
        if t.get("requires_approval"):
            lines.append("      requires_approval: true")
        if t_rules:
            lines.append("      rules:")
            for r in t_rules:
                rule_yaml = yaml.safe_dump(
                    {"if": r.get("condition") or {}, "then": r.get("action") or {},
                     **({"priority": r["priority"]} if r.get("priority", 100) != 100 else {})},
                    default_flow_style=True, sort_keys=False, allow_unicode=True, width=10000,
                ).strip()
                lines.append(f"        - {rule_yaml}")

    workflow_rules = [r for r in bundle.get("rules", []) if not r.get("transition")]
    if workflow_rules:
        lines.append("")
        lines.append("# Workflow-scoped rules are not expressible in the DSL yet;")
        lines.append("# re-add them via the rules editor after import.")

    return "\n".join(lines) + "\n"
