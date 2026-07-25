from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import IsPlatformAdmin, IsWorkflowDesigner

from .models import NotificationLog, NotificationTemplate, TransitionHook, WebhookSubscription
from .serializers import (
    NotificationLogSerializer,
    NotificationTemplateSerializer,
    TransitionHookSerializer,
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


class TransitionHookViewSet(viewsets.ModelViewSet):
    queryset = TransitionHook.objects.select_related("transition").all()
    serializer_class = TransitionHookSerializer
    permission_classes = [IsAuthenticated, IsWorkflowDesigner]
    filterset_fields = ["transition", "trigger", "action", "is_active"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
