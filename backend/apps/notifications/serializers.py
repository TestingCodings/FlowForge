from rest_framework import serializers

from .models import EventTrigger, NotificationLog, NotificationTemplate, WebhookSubscription


class WebhookSubscriptionSerializer(serializers.ModelSerializer):
    workflow_name = serializers.CharField(source="workflow_definition.name", read_only=True, default=None)
    secret = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = WebhookSubscription
        fields = (
            "id",
            "workflow_definition",
            "workflow_name",
            "url",
            "events",
            "secret",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "created_at")

    def validate_events(self, value):
        valid = set(EventTrigger.values)
        invalid = [e for e in value if e not in valid]
        if invalid:
            raise serializers.ValidationError(
                f"Unknown events: {', '.join(invalid)}. Valid: {', '.join(sorted(valid))}"
            )
        return value

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


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
            "event_trigger",
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
