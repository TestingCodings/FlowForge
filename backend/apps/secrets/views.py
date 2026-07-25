from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import require_min_role

from .crypto import SecretsNotConfigured
from .models import Secret
from .serializers import SecretSerializer


class SecretViewSet(viewsets.ModelViewSet):
    """
    Secret store CRUD (docs/HOOKS.md). Values are write-only: create and rotate
    accept a value, nothing ever returns one. workflow_designer+ to manage.
    """
    queryset = Secret.objects.select_related("scope", "created_by").all()
    serializer_class = SecretSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["scope"]
    http_method_names = ["get", "post", "delete", "head", "options"]  # no PUT/PATCH; use rotate

    def create(self, request, *args, **kwargs):
        require_min_role(request.user, "workflow_designer", action="create a secret")
        try:
            return super().create(request, *args, **kwargs)
        except SecretsNotConfigured as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def destroy(self, request, *args, **kwargs):
        require_min_role(request.user, "workflow_designer", action="delete a secret")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="rotate")
    def rotate(self, request, pk=None):
        """Replace a secret's value in place. Body: {"value": "..."}."""
        require_min_role(request.user, "workflow_designer", action="rotate a secret")
        secret = self.get_object()
        value = request.data.get("value")
        if not value:
            return Response({"detail": "A new value is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            secret.set_value(value)
        except SecretsNotConfigured as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        secret.save(update_fields=["ciphertext", "key_version", "updated_at"])
        return Response(SecretSerializer(secret, context={"request": request}).data)
