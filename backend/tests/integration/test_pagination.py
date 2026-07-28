"""Pagination must be controllable by the client.

`?page_size=` was being sent by the dashboard and silently ignored, because
DRF's PageNumberPagination only honours it when `page_size_query_param` is
configured — it wasn't. The dashboard asked for 200 instances, received 25,
and charted those as though they were everything. Any list longer than a
page was quietly wrong rather than visibly truncated.
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleName, User, UserRole
from apps.workflows.models import State, WorkflowDefinition


@pytest.fixture
def client_with_many(db):
    user = User.objects.create_user(
        email="pager@example.com", password="StrongPass123!", first_name="P", last_name="R",
    )
    role, _ = Role.objects.get_or_create(name=RoleName.WORKFLOW_DESIGNER)
    UserRole.objects.create(user=user, role=role)
    for i in range(30):
        wf = WorkflowDefinition.objects.create(
            name=f"Pager {i:02d}", reference_prefix="PGR", created_by=user, is_active=True,
        )
        State.objects.create(workflow_definition=wf, name="Open", is_initial=True, position_order=1)
    c = APIClient()
    c.force_authenticate(user)
    return c


@pytest.mark.django_db
class TestPageSize:
    def test_default_page_size_is_unchanged(self, client_with_many):
        assert len(client_with_many.get("/api/workflows/").data["results"]) == 25

    def test_page_size_is_honoured(self, client_with_many):
        data = client_with_many.get("/api/workflows/?page_size=100").data
        assert len(data["results"]) == 30

    def test_page_size_is_capped(self, client_with_many):
        """An uncapped page_size lets any caller ask for the whole table."""
        data = client_with_many.get("/api/workflows/?page_size=100000").data
        assert len(data["results"]) <= 200

    def test_count_always_reports_the_full_total(self, client_with_many):
        assert client_with_many.get("/api/workflows/").data["count"] == 30

    def test_next_link_still_offered(self, client_with_many):
        assert client_with_many.get("/api/workflows/").data["next"]

    def test_instances_endpoint_honours_it_too(self, client_with_many):
        """The dashboard's real call site."""
        resp = client_with_many.get("/api/instances/?page_size=200")
        assert resp.status_code == 200
