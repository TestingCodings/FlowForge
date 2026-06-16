from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Task
from .serializers import TaskSerializer
from .services import complete_task


class TaskViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        role_names = list(self.request.user.user_roles.values_list("role__name", flat=True))
        queryset = Task.objects.select_related(
            "workflow_instance", "state", "assigned_to_user", "completed_by", "transition"
        ).filter(
            Q(assigned_to_user=self.request.user)
            | Q(assigned_to_role__in=role_names)
            | Q(assigned_to_user__isnull=True, assigned_to_role="")
        )
        return queryset

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        task = self.get_object()
        try:
            task = complete_task(task, request.user)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response(TaskSerializer(task).data, status=status.HTTP_200_OK)
