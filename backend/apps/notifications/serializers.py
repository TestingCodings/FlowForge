from rest_framework import serializers

from .models import NotificationLog, NotificationTemplate


class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        fields = (
            "id",
            "workflow_definition",
            "channel",
            "event_trigger",
            "subject_template",
            "body_template",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class NotificationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationLog
        fields = (
            "id",
            "workflow_instance",
            "channel",
            "recipient",
            "subject",
            "body",
            "status",
            "attempts",
            "error_message",
            "sent_at",
            "created_at",
        )
        read_only_fields = fields
