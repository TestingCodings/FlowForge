"""Tests for the YAML DSL parser, linter, exporter, and compose-yaml endpoint."""
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleName, User, UserRole
from apps.forms.models import FormDefinition
from apps.workflows.dsl import DslError, export_dsl, lint_bundle, parse_dsl
from apps.workflows.models import Rule, WorkflowDefinition
from apps.workflows.portability import export_workflow


GOOD_DSL = """\
workflow: Expense Approval
prefix: EXP
description: Simple expense approval

states:
  - name: Submitted
    sla_hours: 24
  - name: Manager Review
    role: approver
    form:
      fields:
        - {key: amount, type: number, label: Amount, required: true}
  - name: Approved
    terminal: true
  - name: Rejected
    terminal: true

transitions:
  - Submitted -> Manager Review: Submit
  - Manager Review -> Approved:
      name: Approve
      requires_approval: true
      rules:
        - if: {field: amount, op: gt, value: 5000}
          then: {block_transition: true}
  - Manager Review -> Rejected: Reject
"""


class TestParseDsl:
    def test_parses_full_document(self):
        bundle = parse_dsl(GOOD_DSL)
        assert bundle["kind"] == "flowforge.workflow"
        assert bundle["workflow"]["name"] == "Expense Approval"
        assert bundle["workflow"]["reference_prefix"] == "EXP"

        states = {s["name"]: s for s in bundle["states"]}
        assert states["Submitted"]["is_initial"] is True  # first state default
        assert states["Submitted"]["sla_config"] == {"sla_hours": 24}
        assert states["Manager Review"]["task_config"]["default_role"] == "approver"
        assert states["Approved"]["is_terminal"] is True

        transitions = {t["name"]: t for t in bundle["transitions"]}
        assert transitions["Submit"]["from_state"] == "Submitted"
        assert transitions["Approve"]["requires_approval"] is True

        assert len(bundle["rules"]) == 1
        rule = bundle["rules"][0]
        assert rule["transition"] == "Approve"
        assert rule["condition"] == {"field": "amount", "operator": "gt", "value": 5000}
        assert rule["action"] == {"block_transition": True}

        assert len(bundle["forms"]) == 1
        assert bundle["forms"][0]["state"] == "Manager Review"
        assert bundle["forms"][0]["schema"]["fields"][0]["key"] == "amount"

    def test_plain_string_state_shorthand(self):
        bundle = parse_dsl("workflow: X\nstates:\n  - Draft\n  - name: Done\n    terminal: true\n")
        assert bundle["states"][0]["name"] == "Draft"
        assert bundle["states"][0]["is_initial"] is True

    def test_explicit_initial_overrides_first_default(self):
        bundle = parse_dsl(
            "workflow: X\nstates:\n  - A\n  - name: B\n    initial: true\n"
        )
        by_name = {s["name"]: s for s in bundle["states"]}
        assert by_name["A"]["is_initial"] is False
        assert by_name["B"]["is_initial"] is True

    def test_unknown_state_reference_with_hint_and_line(self):
        text = (
            "workflow: X\n"
            "states:\n"
            "  - Approved\n"
            "transitions:\n"
            "  - Approved -> Aproved: Loop\n"
        )
        with pytest.raises(DslError) as exc:
            parse_dsl(text)
        joined = " ".join(exc.value.errors)
        assert "unknown state 'Aproved'" in joined
        assert "did you mean 'Approved'" in joined
        assert "line 5" in joined

    def test_invalid_yaml_reports_line(self):
        with pytest.raises(DslError) as exc:
            parse_dsl("workflow: X\nstates:\n  - name: A\n   bad_indent: true\n")
        assert any("invalid YAML" in e for e in exc.value.errors)

    def test_collects_multiple_errors(self):
        text = (
            "workflow: X\n"
            "states:\n"
            "  - name: A\n"
            "    sla_hours: -5\n"
            "  - name: A\n"
            "transitions:\n"
            "  - A -> Nowhere: Go\n"
        )
        with pytest.raises(DslError) as exc:
            parse_dsl(text)
        joined = " ".join(exc.value.errors)
        assert "sla_hours must be a positive number" in joined
        assert "duplicate state name 'A'" in joined
        assert "unknown state 'Nowhere'" in joined

    def test_unknown_rule_operator(self):
        text = (
            "workflow: X\n"
            "states: [A, B]\n"
            "transitions:\n"
            "  - A -> B:\n"
            "      name: Go\n"
            "      rules:\n"
            "        - if: {field: x, op: wibble, value: 1}\n"
            "          then: {block_transition: true}\n"
        )
        with pytest.raises(DslError) as exc:
            parse_dsl(text)
        assert any("unknown rule operator 'wibble'" in e for e in exc.value.errors)

    def test_missing_workflow_name(self):
        with pytest.raises(DslError) as exc:
            parse_dsl("states: [A]\n")
        assert any("'workflow: <name>' is required" in e for e in exc.value.errors)


class TestLintBundle:
    def test_flags_unreachable_dead_end_and_terminal_issues(self):
        bundle = parse_dsl(
            "workflow: X\n"
            "states:\n"
            "  - Start\n"
            "  - Orphan\n"
            "  - name: End\n"
            "    terminal: true\n"
            "    sla_hours: 4\n"
            "transitions:\n"
            "  - Start -> End: Finish\n"
            "  - End -> Start: Reopen\n"
        )
        warnings = " | ".join(lint_bundle(bundle))
        assert "'Orphan' is unreachable" in warnings
        assert "'Orphan' is a dead end" in warnings
        assert "terminal state 'End' has outgoing transitions" in warnings
        assert "terminal state 'End' has an SLA" in warnings

    def test_no_terminal_state_warning(self):
        bundle = parse_dsl(
            "workflow: X\nstates: [A, B]\ntransitions:\n  - A -> B: Go\n  - B -> A: Back\n"
        )
        assert any("no terminal state" in w for w in lint_bundle(bundle))

    def test_clean_graph_has_no_warnings(self):
        assert lint_bundle(parse_dsl(GOOD_DSL)) == []


@pytest.fixture
def designer_client(db):
    designer = User.objects.create_user(
        email="designer@example.com", password="StrongPass123!",
        first_name="D", last_name="U",
    )
    role = Role.objects.create(name=RoleName.WORKFLOW_DESIGNER)
    UserRole.objects.create(user=designer, role=role)
    client = APIClient()
    login = client.post(
        "/api/auth/login/",
        {"email": designer.email, "password": "StrongPass123!"}, format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return designer, client


@pytest.mark.django_db
class TestComposeYamlEndpoint:
    def test_dry_run_returns_bundle_and_lint_without_saving(self, designer_client):
        _, client = designer_client
        resp = client.post(
            "/api/workflows/compose-yaml/?dry_run=true", {"text": GOOD_DSL}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["valid"] is True
        assert resp.data["name_taken"] is False
        assert len(resp.data["bundle"]["states"]) == 4
        assert not WorkflowDefinition.objects.filter(name="Expense Approval").exists()

    def test_create_builds_full_workflow(self, designer_client):
        _, client = designer_client
        resp = client.post("/api/workflows/compose-yaml/", {"text": GOOD_DSL}, format="json")
        assert resp.status_code == status.HTTP_201_CREATED

        wf = WorkflowDefinition.objects.get(name="Expense Approval")
        assert wf.states.count() == 4
        assert wf.transitions.count() == 3
        assert Rule.objects.filter(workflow_definition=wf).count() == 1
        assert FormDefinition.objects.filter(workflow_definition=wf).count() == 1

    def test_parse_errors_return_400_with_lines(self, designer_client):
        _, client = designer_client
        resp = client.post(
            "/api/workflows/compose-yaml/",
            {"text": "workflow: X\nstates: [A]\ntransitions:\n  - A -> Missing: Go\n"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert any("unknown state 'Missing'" in e for e in resp.data["detail"])

    def test_duplicate_name_refused(self, designer_client):
        designer, client = designer_client
        WorkflowDefinition.objects.create(name="Expense Approval", created_by=designer)
        resp = client.post("/api/workflows/compose-yaml/", {"text": GOOD_DSL}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert any("already exists" in e for e in resp.data["detail"])

    def test_export_yaml_round_trips(self, designer_client):
        _, client = designer_client
        create = client.post("/api/workflows/compose-yaml/", {"text": GOOD_DSL}, format="json")
        wf_id = create.data["id"]

        resp = client.get(f"/api/workflows/{wf_id}/export-yaml/")
        assert resp.status_code == status.HTTP_200_OK
        text = resp.data["text"]
        assert "workflow: Expense Approval" in text

        # The exported text must parse back into an equivalent graph
        bundle = parse_dsl(text)
        assert {s["name"] for s in bundle["states"]} == {
            "Submitted", "Manager Review", "Approved", "Rejected"
        }
        assert {t["name"] for t in bundle["transitions"]} == {"Submit", "Approve", "Reject"}
        assert len(bundle["rules"]) == 1
        assert bundle["rules"][0]["condition"]["operator"] == "gt"
        assert len(bundle["forms"]) == 1


@pytest.mark.django_db
def test_export_dsl_pure_round_trip(designer_client):
    """bundle → DSL → bundle preserves the graph without touching the API."""
    _, client = designer_client
    client.post("/api/workflows/compose-yaml/", {"text": GOOD_DSL}, format="json")
    wf = WorkflowDefinition.objects.get(name="Expense Approval")

    text = export_dsl(export_workflow(wf))
    reparsed = parse_dsl(text)
    original = parse_dsl(GOOD_DSL)

    assert reparsed["states"] == original["states"]
    # Transitions export in model order (alphabetical); compare order-insensitively
    by_name = lambda ts: sorted(ts, key=lambda t: t["name"])
    assert by_name(reparsed["transitions"]) == by_name(original["transitions"])
    assert reparsed["rules"] == original["rules"]
