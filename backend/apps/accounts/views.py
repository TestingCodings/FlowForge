from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Role, RoleName, UserRole
from .serializers import RegisterSerializer, UserSerializer, FlowForgeTokenObtainPairSerializer
from .models import User


class RegisterView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
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

    @action(detail=True, methods=["post"], url_path="roles")
    def set_roles(self, request, pk=None):
        """Replace the user's roles with the provided list. Body: {"roles": ["approver", "participant"]}"""
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
