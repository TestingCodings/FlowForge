import uuid

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsViewer, IsWorkflowDesigner, ReadOnlyOrParticipant, require_min_role

from .models import Rule, State, Transition, WorkflowDefinition
from .serializers import (
    RuleSerializer,
    StateSerializer,
    TransitionSerializer,
    WorkflowDefinitionCreateSerializer,
    WorkflowDefinitionSerializer,
)


class WorkflowDefinitionViewSet(viewsets.ModelViewSet):
    queryset = WorkflowDefinition.objects.all().prefetch_related("states", "transitions", "rules")
    # Reads: viewer+. Writes: workflow_designer+.
    permission_classes = [IsAuthenticated, IsViewer]

    def get_serializer_class(self):
        if self.action == "create":
            return WorkflowDefinitionCreateSerializer
        return WorkflowDefinitionSerializer

    def create(self, request, *args, **kwargs):
        require_min_role(request.user, "workflow_designer", action="create a workflow definition")
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        require_min_role(request.user, "workflow_designer", action="edit a workflow definition")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        require_min_role(request.user, "workflow_designer", action="delete a workflow definition")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="publish-new-version")
    def publish_new_version(self, request, pk=None):
        """
        Mark the current version as published (sets published_at) and create a
        draft clone at version+1 with all states, transitions, and rules copied.
        Returns the new draft workflow definition.
        """
        require_min_role(request.user, "workflow_designer", action="publish a new workflow version")
        original = self.get_object()

        # Stamp published_at on the original if not already set
        if not original.published_at:
            original.published_at = timezone.now()
            original.save(update_fields=["published_at"])

        # Create the new draft
        new_wf = WorkflowDefinition.objects.create(
            name=f"{original.name} (v{original.version + 1} draft)",
            description=original.description,
            reference_prefix=original.reference_prefix,
            version=original.version + 1,
            is_active=False,
            published_at=None,
            parent=original,
            created_by=request.user,
        )

        # Clone states, keeping a map old_state_id → new_state
        state_map = {}
        for state in original.states.all():
            new_state = State.objects.create(
                workflow_definition=new_wf,
                name=state.name,
                display_name=state.display_name,
                is_initial=state.is_initial,
                is_terminal=state.is_terminal,
                position_order=state.position_order,
                sla_config=state.sla_config,
                task_config=state.task_config,
            )
            state_map[str(state.id)] = new_state

        # Clone transitions
        transition_map = {}
        for tr in original.transitions.all():
            new_tr = Transition.objects.create(
                workflow_definition=new_wf,
                from_state=state_map[str(tr.from_state_id)],
                to_state=state_map[str(tr.to_state_id)],
                name=tr.name,
                display_name=tr.display_name,
                requires_approval=tr.requires_approval,
            )
            transition_map[str(tr.id)] = new_tr

        # Clone rules
        for rule in original.rules.all():
            Rule.objects.create(
                workflow_definition=new_wf,
                transition=transition_map[str(rule.transition_id)] if rule.transition_id else None,
                condition=rule.condition,
                action=rule.action,
                priority=rule.priority,
            )

        return Response(WorkflowDefinitionSerializer(new_wf).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="version-history")
    def version_history(self, request, pk=None):
        """Return all versions in the chain (ancestors + self + descendants)."""
        wf = self.get_object()

        # Walk up to root
        root = wf
        while root.parent_id:
            root = root.parent

        # BFS down from root
        versions = []
        queue = [root]
        while queue:
            current = queue.pop(0)
            versions.append(current)
            queue.extend(current.child_versions.all())

        return Response(WorkflowDefinitionSerializer(versions, many=True).data)

    @action(detail=True, methods=["patch"], url_path="ui-schema")
    def update_ui_schema(self, request, pk=None):
        """Set the presentation schema (Layer 2). workflow_designer+."""
        require_min_role(request.user, "workflow_designer", action="edit workflow UI schema")
        wf = self.get_object()
        ui_schema = request.data.get("ui_schema")
        if not isinstance(ui_schema, dict):
            return Response({"detail": "ui_schema must be an object."}, status=400)
        shell = ui_schema.get("shell", "list")
        if shell not in ("list", "kanban"):
            return Response({"detail": f"Unknown shell '{shell}'. Valid: list, kanban."}, status=400)
        wf.ui_schema = ui_schema
        wf.save(update_fields=["ui_schema", "updated_at"])
        return Response(WorkflowDefinitionSerializer(wf).data)

    @action(detail=True, methods=["get"], url_path="export")
    def export_bundle(self, request, pk=None):
        """Download the workflow as a portable JSON bundle (Layer 3)."""
        from django.http import JsonResponse

        from .portability import export_workflow

        wf = self.get_object()
        bundle = export_workflow(wf)
        response = JsonResponse(bundle, json_dumps_params={"indent": 2})
        safe_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in wf.name.lower())
        response["Content-Disposition"] = f'attachment; filename="{safe_name}-v{wf.version}.flowforge.json"'
        return response

    @action(detail=False, methods=["post"], url_path="import")
    def import_bundle(self, request):
        """Create a workflow from a bundle. workflow_designer+.

        POST body: the bundle JSON, optionally wrapped as {"bundle": ..., "name": "New Name"}.
        """
        from .portability import BundleError, import_workflow

        require_min_role(request.user, "workflow_designer", action="import a workflow")
        bundle = request.data.get("bundle") if "bundle" in request.data else request.data
        rename = request.data.get("name") if "bundle" in request.data else None
        if not isinstance(bundle, dict):
            return Response({"detail": "Request body must be a bundle object."}, status=400)
        try:
            wf = import_workflow(bundle, created_by=request.user, rename=rename)
        except BundleError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(WorkflowDefinitionSerializer(wf).data, status=status.HTTP_201_CREATED)


class StateViewSet(viewsets.ModelViewSet):
    queryset = State.objects.select_related("workflow_definition").all()
    serializer_class = StateSerializer
    permission_classes = [IsAuthenticated]


class TransitionViewSet(viewsets.ModelViewSet):
    queryset = Transition.objects.select_related("workflow_definition", "from_state", "to_state").all()
    serializer_class = TransitionSerializer
    permission_classes = [IsAuthenticated]


class RuleViewSet(viewsets.ModelViewSet):
    queryset = Rule.objects.select_related("workflow_definition", "transition").all()
    serializer_class = RuleSerializer
    # Rules are config — workflow_designer+ for all writes, viewer+ for reads
    permission_classes = [IsAuthenticated, IsViewer]

    def create(self, request, *args, **kwargs):
        require_min_role(request.user, "workflow_designer", action="create a rule")
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        require_min_role(request.user, "workflow_designer", action="edit a rule")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        require_min_role(request.user, "workflow_designer", action="delete a rule")
        return super().destroy(request, *args, **kwargs)
