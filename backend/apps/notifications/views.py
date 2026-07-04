from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import IsPlatformAdmin, IsWorkflowDesigner

from .models import NotificationLog, NotificationTemplate, WebhookSubscription
from .serializers import (
    NotificationLogSerializer,
    NotificationTemplateSerializer,
    WebhookSubscriptionSerializer,
)


class NotificationTemplateViewSet(viewsets.ModelViewSet):
    queryset = NotificationTemplate.objects.select_related("workflow_definition").all()
    serializer_class = NotificationTemplateSerializer
    permission_classes = [IsAuthenticated, IsPlatformAdmin]


class NotificationLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NotificationLog.objects.select_related("workflow_instance").all()
    serializer_class = NotificationLogSerializer
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    filterset_fields = ["workflow_instance", "event_trigger", "status", "channel"]


class WebhookSubscriptionViewSet(viewsets.ModelViewSet):
    queryset = WebhookSubscription.objects.select_related("workflow_definition").all()
    serializer_class = WebhookSubscriptionSerializer
    permission_classes = [IsAuthenticated, IsWorkflowDesigner]
    filterset_fields = ["workflow_definition", "is_active"]
