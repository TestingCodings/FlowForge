import uuid

from django.db import transaction
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

    @action(detail=True, methods=["put"], url_path="compose")
    def compose(self, request, pk=None):
        """
        Diff-update the full graph (workflow metadata + states + transitions)
        from the visual builder in one atomic request.

        Payload states/transitions may carry an `id` — those are updated in
        place (preserving attached forms and rules); entries without an id are
        created; existing rows absent from the payload are deleted.

        Refused with 409 if the workflow has instances — publish a new
        version instead (the builder offers this flow on 409).
        """
        require_min_role(request.user, "workflow_designer", action="edit a workflow definition")
        workflow = self.get_object()

        instance_count = workflow.instances.count()
        if instance_count:
            return Response(
                {
                    "detail": (
                        f"This workflow has {instance_count} instance(s); its graph cannot be "
                        "edited in place. Publish a new version and edit that instead."
                    ),
                    "instance_count": instance_count,
                },
                status=status.HTTP_409_CONFLICT,
            )

        states_payload = request.data.get("states", [])
        transitions_payload = request.data.get("transitions", [])
        errors = []
        if not states_payload:
            errors.append("At least one state is required.")
        initials = [s for s in states_payload if s.get("is_initial")]
        if len(initials) != 1:
            errors.append("Exactly one state must be marked as initial.")
        names = [str(s.get("name", "")).strip() for s in states_payload]
        if any(not n for n in names):
            errors.append("All states must have a name.")
        if len(set(names)) != len(names):
            errors.append("State names must be unique.")
        for tr in transitions_payload:
            if tr.get("from_state") not in names or tr.get("to_state") not in names:
                errors.append(f"Transition '{tr.get('name')}' references an unknown state.")
        if errors:
            return Response({"detail": errors}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            for field in ("name", "description", "reference_prefix", "is_active"):
                if field in request.data:
                    setattr(workflow, field, request.data[field])
            workflow.save()

            existing_states = {str(s.id): s for s in workflow.states.all()}
            payload_state_ids = {str(s["id"]) for s in states_payload if s.get("id")}

            # Delete states removed from the canvas (cascades their forms/transitions)
            for sid, state in existing_states.items():
                if sid not in payload_state_ids:
                    state.delete()

            # Two-pass update dodges the unique (workflow, name) / (workflow,
            # position_order) constraints when states are renamed or reordered
            # into each other's slots.
            kept = [s for s in states_payload if str(s.get("id", "")) in existing_states]
            for i, sp in enumerate(kept):
                state = existing_states[str(sp["id"])]
                state.name = f"__tmp__{uuid.uuid4().hex[:12]}"
                state.position_order = 10000 + i
                state.save(update_fields=["name", "position_order"])

            state_by_name = {}
            for i, sp in enumerate(states_payload, start=1):
                shared = dict(
                    name=str(sp["name"]).strip(),
                    display_name=sp.get("display_name", ""),
                    is_initial=sp.get("is_initial", False),
                    is_terminal=sp.get("is_terminal", False),
                    position_order=sp.get("position_order", i),
                    sla_config=sp.get("sla_config", {}),
                    task_config=sp.get("task_config", {}),
                    canvas_position=sp.get("canvas_position", {}),
                )
                sid = str(sp.get("id", ""))
                if sid in existing_states:
                    state = existing_states[sid]
                    for k, v in shared.items():
                        setattr(state, k, v)
                    state.save()
                else:
                    state = State.objects.create(workflow_definition=workflow, **shared)
                state_by_name[state.name] = state

            existing_transitions = {str(t.id): t for t in workflow.transitions.all()}
            payload_transition_ids = {str(t["id"]) for t in transitions_payload if t.get("id")}
            for tid, tr in existing_transitions.items():
                if tid not in payload_transition_ids:
                    tr.delete()  # cascades transition-scoped rules

            for tp in transitions_payload:
                shared = dict(
                    from_state=state_by_name[tp["from_state"]],
                    to_state=state_by_name[tp["to_state"]],
                    name=tp.get("name", "Transition"),
                    display_name=tp.get("display_name", ""),
                    requires_approval=tp.get("requires_approval", False),
                )
                tid = str(tp.get("id", ""))
                if tid in existing_transitions:
                    tr = existing_transitions[tid]
                    for k, v in shared.items():
                        setattr(tr, k, v)
                    tr.save()
                else:
                    Transition.objects.create(workflow_definition=workflow, **shared)

        workflow.refresh_from_db()
        return Response(WorkflowDefinitionSerializer(workflow).data)

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
        from .ui_schema import validate_ui_schema

        require_min_role(request.user, "workflow_designer", action="edit workflow UI schema")
        wf = self.get_object()
        ui_schema = request.data.get("ui_schema")
        error = validate_ui_schema(ui_schema)
        if error:
            return Response({"detail": error}, status=400)
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

    @action(detail=False, methods=["post"], url_path="compose-yaml")
    def compose_yaml(self, request):
        """Create a workflow from DSL text (docs/BUILDER.md Part 3).

        POST body: {"text": "<yaml dsl>"}. Pass ?dry_run=true to validate
        and preview without saving — returns the parsed graph plus lint
        warnings so editors can live-preview while typing.
        """
        from .dsl import DslError, lint_bundle, parse_dsl
        from .portability import BundleError, import_workflow

        require_min_role(request.user, "workflow_designer", action="create a workflow from YAML")
        text = request.data.get("text")
        if not isinstance(text, str) or not text.strip():
            return Response({"detail": ["'text' with the YAML document is required."]}, status=400)

        try:
            bundle = parse_dsl(text)
        except DslError as exc:
            return Response({"detail": exc.errors}, status=400)

        lint = lint_bundle(bundle)
        dry_run = str(request.query_params.get("dry_run", "")).lower() in {"1", "true", "yes"}
        if dry_run:
            name_taken = WorkflowDefinition.objects.filter(name=bundle["workflow"]["name"]).exists()
            return Response({
                "valid": True,
                "bundle": bundle,
                "lint": lint,
                "name_taken": name_taken,
            })

        try:
            wf = import_workflow(bundle, created_by=request.user)
        except BundleError as exc:
            return Response({"detail": [str(exc)]}, status=400)
        data = WorkflowDefinitionSerializer(wf).data
        data["lint"] = lint
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="export-yaml")
    def export_yaml(self, request, pk=None):
        """Render the workflow as DSL text for viewing/copying/re-import."""
        from .dsl import export_dsl
        from .portability import export_workflow

        wf = self.get_object()
        return Response({"text": export_dsl(export_workflow(wf))})

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
