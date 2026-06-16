from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import IsPlatformAdmin

from .models import NotificationLog, NotificationTemplate
from .serializers import NotificationLogSerializer, NotificationTemplateSerializer


class NotificationTemplateViewSet(viewsets.ModelViewSet):
    queryset = NotificationTemplate.objects.select_related("workflow_definition").all()
    serializer_class = NotificationTemplateSerializer
    permission_classes = [IsAuthenticated, IsPlatformAdmin]


class NotificationLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NotificationLog.objects.select_related("workflow_instance").all()
    serializer_class = NotificationLogSerializer
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
