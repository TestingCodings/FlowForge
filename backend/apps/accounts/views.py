from django.conf import settings
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Role, RoleName, UserRole
from .permissions import IsPlatformAdmin, require_capability
from rest_framework.exceptions import PermissionDenied
from .serializers import (
    FlowForgeTokenObtainPairSerializer,
    MeSerializer,
    RegisterSerializer,
    RoleSerializer,
    UserSerializer,
)
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
    # MeSerializer, not UserSerializer: this is the only place the resolved
    # capability set belongs. Putting it on the user list would leak what
    # every other person may do, and cost a query per row to say it.
    serializer_class = MeSerializer

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

    @action(detail=True, methods=["post"], url_path="roles",
            permission_classes=[IsAuthenticated])
    def set_roles(self, request, pk=None):
        """Replace a user's roles. Body: {"roles": ["approver", "site_manager"]}

        Validated against the Role table rather than the RoleName enum. That
        distinction is the feature: while this checked the enum, a custom
        role could be created but never assigned to anyone.

        Two guards, both of which make the difference between a role system
        and a footgun:

        * **Nobody may assign above their own rank.** Any role carrying
          user.assign_roles would otherwise be a route to platform admin:
          grant yourself the higher role and you are done.
        * **The last holder of user.assign_roles cannot lose it.** Locking
          everyone out of role management is unrecoverable through the API,
          so it is refused rather than warned about.
        """
        require_capability(request.user, "user.assign_roles", action="change a user's roles")
        user = self.get_object()
        requested = request.data.get("roles", [])
        if not isinstance(requested, list):
            return Response({"detail": "roles must be a list of role keys."},
                            status=status.HTTP_400_BAD_REQUEST)

        roles = list(Role.objects.filter(key__in=requested))
        missing = set(requested) - {r.key for r in roles}
        if missing:
            return Response(
                {"detail": f"Unknown role(s): {', '.join(sorted(missing))}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ceiling = max(
            request.user.user_roles.select_related("role")
            .values_list("role__rank", flat=True),
            default=0,
        )
        too_senior = [r.label for r in roles if r.rank > ceiling]
        if too_senior:
            return Response(
                {"detail": (
                    f"You cannot assign a role more senior than your own: "
                    f"{', '.join(sorted(too_senior))}."
                )},
                status=status.HTTP_403_FORBIDDEN,
            )

        if self._would_orphan_role_management(user, roles):
            return Response(
                {"detail": (
                    "This would remove the last user who can manage roles. "
                    "Give another user that ability first."
                )},
                status=status.HTTP_409_CONFLICT,
            )

        UserRole.objects.filter(user=user).delete()
        for role in roles:
            UserRole.objects.create(user=user, role=role)

        user.refresh_from_db()
        return Response(UserSerializer(user).data)

    @staticmethod
    def _would_orphan_role_management(user, new_roles) -> bool:
        """True if this change leaves nobody able to assign roles."""
        CAP = "user.assign_roles"
        keeps_it = any(CAP in (r.capabilities or []) for r in new_roles)
        if keeps_it:
            return False

        # Which roles grant it is resolved in Python rather than with a
        # `capabilities__contains` lookup: that lookup is unsupported on
        # SQLite, so the query would work on CI's Postgres and fail in local
        # development. There are a handful of roles, so the cost is nil.
        granting = [
            r.id for r in Role.objects.all() if CAP in (r.capabilities or [])
        ]
        if not granting:
            return False

        others = (
            UserRole.objects.filter(role_id__in=granting).exclude(user=user).exists()
        )
        if others:
            return False

        # Only blocks when this user currently holds it; demoting somebody who
        # never had it cannot orphan anything.
        return user.user_roles.filter(role_id__in=granting).exists()


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


class RoleViewSet(viewsets.ModelViewSet):
    """Manage roles (docs/ROLES.md step 3).

    Reading is open to any signed-in user, because role badges and pickers
    render for everyone. Writing needs `workspace.manage`: composing roles is
    administering the install, not designing workflows.

    The guards here matter more than the CRUD:

    * **System roles are immutable.** The built-in five are what every
      existing permission check assumes; editing one silently changes the
      meaning of the whole install, and deleting one would strip permissions
      from people without anyone choosing to.
    * **A role cannot outrank its creator.** Otherwise creating a role is a
      route to escalation: make one above yourself, assign it to yourself,
      and the rank cap on assignment means nothing.
    * **A role in use cannot be deleted.** Same reasoning as the system-role
      guard, and it fails with 409 rather than cascading.
    """

    queryset = Role.objects.all().order_by("-rank", "key")
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated]

    def _max_assignable_rank(self, user) -> int:
        """The highest rank the caller holds. Nobody may exceed their own."""
        ranks = user.user_roles.select_related("role").values_list("role__rank", flat=True)
        return max(ranks, default=0)

    def create(self, request, *args, **kwargs):
        require_capability(request.user, "workspace.manage", action="create a role")
        rank = int(request.data.get("rank") or 0)
        ceiling = self._max_assignable_rank(request.user)
        if rank > ceiling:
            return Response(
                {"detail": (
                    f"A role cannot outrank you. Your highest rank is {ceiling}; "
                    f"this role asks for {rank}."
                )},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        require_capability(request.user, "workspace.manage", action="edit a role")
        if self.get_object().is_system:
            raise PermissionDenied(
                "Built-in roles cannot be edited. Create a custom role instead."
            )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, partial=True, **kwargs)

    def destroy(self, request, *args, **kwargs):
        require_capability(request.user, "workspace.manage", action="delete a role")
        role = self.get_object()
        if role.is_system:
            raise PermissionDenied("Built-in roles cannot be deleted.")

        holders = role.user_roles.count()
        if holders:
            return Response(
                {"detail": (
                    f"'{role.label}' is in use by {holders} user(s) and cannot be "
                    "deleted. Reassign them first."
                )},
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)
