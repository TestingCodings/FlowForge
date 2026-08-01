from django.conf import settings
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Role, RoleName, UserRole
from .permissions import IsPlatformAdmin, require_capability
from .serializers import RegisterSerializer, UserSerializer, FlowForgeTokenObtainPairSerializer
from .models import User


class RegisterView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        # The public demo issues accounts rather than accepting them
        # (docs/DEPLOYMENT.md §2.2). Absent the setting — i.e. every ordinary
        # deployment — registration is open, so this is inert by default.
        if not getattr(settings, "DEMO_REGISTRATION_ENABLED", True):
            return Response(
                {"detail": "Registration is disabled on this demo. "
                           "Sign in with one of the demo accounts shown on the login page."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = FlowForgeTokenObtainPairSerializer


class MeView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.prefetch_related("user_roles__role").filter(is_active=True).order_by("first_name", "last_name")
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["post"], url_path="demo-switch", permission_classes=[IsAuthenticated, IsPlatformAdmin])
    def demo_switch(self, request):
        """Issue JWT tokens for another user without a password. Platform admin only."""
        user_id = request.data.get("user_id")
        if not user_id:
            return Response({"detail": "user_id required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            target = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        refresh = RefreshToken.for_user(target)
        return Response({
            "access":  str(refresh.access_token),
            "refresh": str(refresh),
            "user":    UserSerializer(target).data,
        })

    @action(detail=True, methods=["post"], url_path="roles", permission_classes=[IsAuthenticated, IsPlatformAdmin])
    def set_roles(self, request, pk=None):
        """Replace the user's roles. Platform admin only. Body: {"roles": ["approver", "participant"]}"""
        user = self.get_object()
        role_names = request.data.get("roles", [])
        valid = {r[0] for r in RoleName.choices}
        invalid = [r for r in role_names if r not in valid]
        if invalid:
            return Response({"detail": f"Invalid roles: {invalid}"}, status=status.HTTP_400_BAD_REQUEST)

        UserRole.objects.filter(user=user).delete()
        for name in role_names:
            role, _ = Role.objects.get_or_create(name=name)
            UserRole.objects.create(user=user, role=role)

        return Response(UserSerializer(user).data)


class WorkspaceView(generics.GenericAPIView):
    """Singleton workspace config: any authenticated user reads, platform_admin writes."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import Workspace

        ws = Workspace.current()
        return Response({
            "id": str(ws.id),
            "name": ws.name,
            "tagline": ws.tagline,
            "logo_url": ws.logo_url,
            "ui_config": ws.ui_config,
            "updated_at": ws.updated_at.isoformat(),
            # Lets the frontend warn that data is rebuilt nightly, so a
            # visitor doesn't mistake the reset for losing their work. Empty
            # on every non-demo deployment, which renders no banner.
            "demo_notice": (
                getattr(settings, "DEMO_RESET_NOTICE", "")
                if getattr(settings, "DEMO_MODE", False) else ""
            ),
        })

    def put(self, request):
        from .models import Workspace
        require_capability(request.user, "workspace.manage", action="edit workspace settings")
        ws = Workspace.current()
        for field in ("name", "tagline", "logo_url"):
            if field in request.data:
                setattr(ws, field, request.data[field] or "")
        if "ui_config" in request.data:
            ui = request.data["ui_config"]
            if not isinstance(ui, dict):
                return Response({"detail": "ui_config must be an object."}, status=400)
            theme = ui.get("theme", {})
            if not isinstance(theme, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in theme.items()
            ):
                return Response(
                    {"detail": "ui_config.theme must map token names to colour strings."}, status=400
                )
            for key, valid in (
                ("font", {"inter", "system", "serif", "mono"}),
                ("date_format", {"locale", "dd/mm/yyyy", "mm/dd/yyyy", "yyyy-mm-dd"}),
                # VISION Layer 1: workspace-wide fallback shell, UI density, language
                # Keep in sync with VALID_SHELLS in apps/workflows/ui_schema.py.
                ("default_view", {"list", "kanban", "table", "calendar", "matrix",
                                  "stepped_form", "scene"}),
                ("density", {"comfortable", "compact"}),
                # Keep in sync with LOCALES in frontend/src/i18n/index.tsx.
                ("locale", {"en-GB", "es-ES", "fr-FR", "de-DE"}),
            ):
                if key in ui and ui[key] not in valid:
                    return Response(
                        {"detail": f"ui_config.{key} must be one of: {', '.join(sorted(valid))}."},
                        status=400,
                    )
            ws.ui_config = ui
        ws.save()
        return self.get(request)
