from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Role, User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "password", "password_confirm")

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "full_name", "roles", "date_joined")
        read_only_fields = ("id", "date_joined")

    def get_roles(self, obj):
        return list(obj.user_roles.select_related("role").values_list("role__name", flat=True))


class FlowForgeTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Extend the default JWT login response to include basic user info."""

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


class RoleSerializer(serializers.ModelSerializer):
    """Roles as an editable resource (docs/ROLES.md step 3).

    `key` is read-only after creation: app bundles reference roles by key, so
    a rename would silently break every app exported before it. `is_system`
    is read-only always, since a client must not be able to promote their own
    role into an undeletable one.
    """

    assigned_count = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = (
            "id", "key", "label", "capabilities", "rank",
            "is_system", "description", "assigned_count",
        )
        read_only_fields = ("id", "is_system", "assigned_count")

    def get_assigned_count(self, role) -> int:
        return role.user_roles.count()

    def validate_capabilities(self, value):
        from .models import CAPABILITIES

        if not isinstance(value, list):
            raise serializers.ValidationError("capabilities must be a list.")
        unknown = [c for c in value if c not in CAPABILITIES]
        if unknown:
            # Refused rather than dropped: a silently ignored capability
            # produces a role that looks right and permits nothing.
            raise serializers.ValidationError(
                f"Unknown capabilities: {', '.join(unknown)}. "
                f"Valid: {', '.join(sorted(CAPABILITIES))}."
            )
        return value

    def update(self, instance, validated_data):
        # Belt and braces alongside read_only_fields, since `key` arriving
        # through another code path would be a quiet break.
        validated_data.pop("key", None)
        return super().update(instance, validated_data)
