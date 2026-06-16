from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Rule, State, Transition, WorkflowDefinition
from .serializers import (
    RuleSerializer,
    StateSerializer,
    TransitionSerializer,
    WorkflowDefinitionCreateSerializer,
    WorkflowDefinitionSerializer,
)


class WorkflowDefinitionViewSet(viewsets.ModelViewSet):
    queryset = WorkflowDefinition.objects.all().prefetch_related("states", "transitions")
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return WorkflowDefinitionCreateSerializer
        return WorkflowDefinitionSerializer


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
    permission_classes = [IsAuthenticated]
