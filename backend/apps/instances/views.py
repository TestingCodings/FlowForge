from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.workflows.engine import WorkflowTransitionError, perform_transition

from .models import WorkflowInstance
from .serializers import TransitionRequestSerializer, WorkflowInstanceSerializer


class WorkflowInstanceViewSet(viewsets.ModelViewSet):
    queryset = WorkflowInstance.objects.select_related("workflow_definition", "current_state", "created_by").all()
    serializer_class = WorkflowInstanceSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request, pk=None):
        instance = self.get_object()
        serializer = TransitionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = perform_transition(instance, serializer.validated_data["transition_id"])
        except WorkflowTransitionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = WorkflowInstanceSerializer(instance).data
        payload["transition_applied"] = {
            "id": str(result.transition.id),
            "name": result.transition.name,
            "from_state": result.transition.from_state.name,
            "to_state": result.transition.to_state.name,
        }
        return Response(payload, status=status.HTTP_200_OK)
