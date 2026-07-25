"""Integration tests for the cross-instance topology endpoint."""
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleName, User, UserRole
from apps.instances.models import InstanceRelationship, WorkflowInstance
from apps.workflows.models import State, WorkflowDefinition


@pytest.fixture
def client_and_data(db):
    user = User.objects.create_user(
        email="topo@example.com", password="StrongPass123!",
        first_name="Topo", last_name="User",
    )
    role = Role.objects.create(name=RoleName.WORKFLOW_DESIGNER)
    UserRole.objects.create(user=user, role=role)

    # Two workflows so the graph crosses workflow boundaries.
    infra = WorkflowDefinition.objects.create(name="Infrastructure", created_by=user)
    State.objects.create(workflow_definition=infra, name="Active", is_initial=True, position_order=1)
    hosts = WorkflowDefinition.objects.create(
        name="Hosts", created_by=user, ui_schema={"title_field": "hostname"},
    )
    State.objects.create(workflow_definition=hosts, name="Online", is_initial=True, position_order=1)

    vm = WorkflowInstance.objects.create(workflow_definition=infra, created_by=user)
    host = WorkflowInstance.objects.create(
        workflow_definition=hosts, created_by=user, metadata_json={"hostname": "test-host-3"},
    )
    device_a = WorkflowInstance.objects.create(workflow_definition=hosts, created_by=user, parent=host)
    device_b = WorkflowInstance.objects.create(workflow_definition=hosts, created_by=user, parent=host)

    InstanceRelationship.objects.create(
        from_instance=vm, to_instance=host, rel_type="hosts", created_by=user,
    )

    client = APIClient()
    login = client.post(
        "/api/auth/login/",
        {"email": user.email, "password": "StrongPass123!"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return client, vm, host, device_a, device_b


@pytest.mark.django_db
def test_rooted_topology_walks_relationships_and_containment(client_and_data):
    client, vm, host, device_a, device_b = client_and_data

    resp = client.get(f"/api/topology/?root={vm.id}&depth=2")
    assert resp.status_code == status.HTTP_200_OK

    node_ids = {n["id"] for n in resp.data["nodes"]}
    # VM → host (relationship), host → device_a/device_b (containment) within 2 hops
    assert str(vm.id) in node_ids
    assert str(host.id) in node_ids
    assert str(device_a.id) in node_ids
    assert str(device_b.id) in node_ids

    kinds = {e["kind"] for e in resp.data["edges"]}
    assert "relationship" in kinds
    assert "containment" in kinds

    # The host node carries its title_field-resolved title
    host_node = next(n for n in resp.data["nodes"] if n["id"] == str(host.id))
    assert host_node["title"] == "test-host-3"
    assert host_node["workflow"] == "Hosts"


@pytest.mark.django_db
def test_depth_limit_bounds_the_walk(client_and_data):
    client, vm, host, device_a, device_b = client_and_data

    # depth=1 from the VM reaches the host but not the host's children
    resp = client.get(f"/api/topology/?root={vm.id}&depth=1")
    node_ids = {n["id"] for n in resp.data["nodes"]}
    assert str(host.id) in node_ids
    assert str(device_a.id) not in node_ids


@pytest.mark.django_db
def test_rel_types_filter_excludes_containment(client_and_data):
    client, vm, host, device_a, device_b = client_and_data

    resp = client.get(f"/api/topology/?root={vm.id}&depth=3&rel_types=hosts")
    kinds = {e["kind"] for e in resp.data["edges"]}
    assert kinds == {"relationship"}  # containment excluded when rel_types is set


@pytest.mark.django_db
def test_whole_estate_topology(client_and_data):
    client, vm, host, device_a, device_b = client_and_data

    resp = client.get("/api/topology/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["root"] is None
    # All four instances present; the hosts relationship + two containment edges
    assert len(resp.data["nodes"]) == 4
    edge_kinds = sorted(e["kind"] for e in resp.data["edges"])
    assert edge_kinds == ["containment", "containment", "relationship"]


@pytest.mark.django_db
def test_topology_requires_auth(db):
    resp = APIClient().get("/api/topology/")
    assert resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
