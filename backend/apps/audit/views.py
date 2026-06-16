from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import IsPlatformAdmin

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogAdminViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related("workflow_instance", "actor").all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["action_type", "actor", "created_at"]


class AuditTrailByInstanceView(generics.ListAPIView):
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return AuditLog.objects.select_related("workflow_instance", "actor").filter(
            workflow_instance_id=self.kwargs["instance_id"]
        )
