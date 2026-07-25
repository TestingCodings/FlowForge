from rest_framework import serializers

from apps.workflows.models import WorkflowDefinition
from .models import Secret


class SecretSerializer(serializers.ModelSerializer):
    """Write-only for `value`; the API never returns a secret's plaintext."""
    value = serializers.CharField(write_only=True, trim_whitespace=False)
    # default=None keeps scope optional even though it's part of the
    # (scope, name) unique constraint, whose UniqueTogetherValidator would
    # otherwise force every constraint field to be supplied.
    scope = serializers.PrimaryKeyRelatedField(
        queryset=WorkflowDefinition.objects.all(), required=False, allow_null=True, default=None,
    )
    scope_name = serializers.CharField(source="scope.name", read_only=True, default=None)

    class Meta:
        model = Secret
        fields = (
            "id", "name", "scope", "scope_name", "value",
            "created_by", "created_at", "updated_at", "last_used_at",
        )
        read_only_fields = ("id", "created_by", "created_at", "updated_at", "last_used_at")

    def validate_value(self, value):
        if not value:
            raise serializers.ValidationError("A secret value is required.")
        return value

    def create(self, validated_data):
        plaintext = validated_data.pop("value")
        secret = Secret(**validated_data, created_by=self.context["request"].user)
        secret.set_value(plaintext)  # encrypts; ciphertext/key_version set here
        secret.save()
        return secret
