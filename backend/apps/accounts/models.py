import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email address is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        db_table = "accounts_user"
        ordering = ["email"]

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


class RoleName(models.TextChoices):
    PLATFORM_ADMIN = "platform_admin", "Platform Admin"
    WORKFLOW_DESIGNER = "workflow_designer", "Workflow Designer"
    PARTICIPANT = "participant", "Participant"
    APPROVER = "approver", "Approver"
    VIEWER = "viewer", "Viewer"


class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, choices=RoleName.choices, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "accounts_role"

    def __str__(self):
        return self.get_name_display()


class UserRole(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_roles")
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="assigned_roles"
    )

    class Meta:
        db_table = "accounts_user_role"
        unique_together = ("user", "role")

    def __str__(self):
        return f"{self.user.email} — {self.role}"


DEFAULT_THEME = {
    "accent": "#6366f1",
    "accent_light": "#818cf8",
    "bg_base": "#0d1117",
    "bg_surface": "#161b22",
    "bg_elevated": "#21262d",
    "text_primary": "#e6edf3",
    "success": "#3fb950",
    "warning": "#d29922",
    "danger": "#f85149",
}


class Workspace(models.Model):
    """Singleton platform-level branding and UI configuration (VISION Layer 1)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, default="FlowForge")
    tagline = models.CharField(max_length=150, blank=True, default="Workflow Automation")
    logo_url = models.URLField(max_length=500, blank=True)
    ui_config = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "workspace"

    def __str__(self):
        return self.name

    @classmethod
    def current(cls):
        ws = cls.objects.first()
        if ws is None:
            ws = cls.objects.create(ui_config={"theme": DEFAULT_THEME})
        return ws
