from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True)

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "workflow_instance",
            "actor",
            "actor_email",
            "action_type",
            "from_state",
            "to_state",
            "payload",
            "ip_address",
            "user_agent",
            "created_at",
        )
        read_only_fields = fields
