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


# The closed vocabulary of things a role may be permitted to do
# (docs/ROLES.md §2.1). Role *names* become free text so a client can have a
# "Site Manager"; capabilities stay fixed because each one corresponds to a
# real check in the code. Inverting it this way is what makes custom roles
# safe: a creator composes from these, and can never invent a permission
# nothing enforces.
CAPABILITIES = (
    "workflow.view", "workflow.design", "workflow.publish",
    "instance.view", "instance.create", "instance.transition",
    "instance.approve", "instance.comment", "instance.metadata",
    "form.submit", "media.upload", "media.delete",
    "user.view", "user.create", "user.assign_roles",
    "secret.manage", "hook.manage", "audit.view",
    "workspace.manage",
)

# What each built-in role may do, mirroring the checks that exist today so
# this step changes no behaviour. `rank` supports the "this role or above"
# comparisons already scattered through the code (viewer+, designer+); it is
# a convenience over capabilities, never a parallel source of authority.
SYSTEM_ROLES = {
    "platform_admin": {
        "label": "Platform Admin", "rank": 50, "capabilities": list(CAPABILITIES),
    },
    "workflow_designer": {
        "label": "Workflow Designer", "rank": 40,
        "capabilities": [
            "workflow.view", "workflow.design", "workflow.publish",
            "instance.view", "instance.create", "instance.transition",
            "instance.approve", "instance.comment", "instance.metadata",
            "form.submit", "media.upload", "media.delete",
            "user.view", "secret.manage", "hook.manage", "audit.view",
        ],
    },
    "approver": {
        "label": "Approver", "rank": 30,
        "capabilities": [
            "workflow.view", "instance.view", "instance.create",
            "instance.transition", "instance.approve", "instance.comment",
            "instance.metadata", "form.submit", "media.upload", "user.view",
        ],
    },
    "participant": {
        "label": "Participant", "rank": 20,
        "capabilities": [
            "workflow.view", "instance.view", "instance.create",
            "instance.transition", "instance.comment", "instance.metadata",
            "form.submit", "media.upload", "user.view",
        ],
    },
    "viewer": {
        "label": "Viewer", "rank": 10,
        "capabilities": ["workflow.view", "instance.view", "instance.comment", "user.view"],
    },
}


class Role(models.Model):
    """A role, as data rather than an enum (docs/ROLES.md).

    `name` is retained and kept equal to `key` because every permission check
    still reads it. Migrating those is the next step; until then the two must
    not diverge or a check silently stops matching.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Legacy: still the field permission checks compare against.
    name = models.CharField(max_length=50, unique=True)
    # Stable identifier a bundle can reference across installs.
    key = models.SlugField(max_length=50, unique=True)
    label = models.CharField(max_length=100, blank=True)
    capabilities = models.JSONField(default=list, blank=True)
    # Built-in roles cannot be deleted; a client's own roles can.
    is_system = models.BooleanField(default=False)
    rank = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "accounts_role"

    def __str__(self):
        return self.label or self.key

    def save(self, *args, **kwargs):
        """Fill the new fields from `name` when they weren't supplied.

        Every existing caller does `Role.objects.create(name=RoleName.X)` and
        knows nothing about keys or capabilities. Defaulting here keeps all of
        them working and, more importantly, keeps them *correct* — a role
        created the old way still gets the right capabilities, so this step
        cannot quietly produce roles that are permitted nothing.
        """
        if not self.key:
            self.key = self.name
        spec = SYSTEM_ROLES.get(self.key)
        if spec:
            if not self.label:
                self.label = spec["label"]
            if not self.capabilities:
                self.capabilities = list(spec["capabilities"])
            if not self.rank:
                self.rank = spec["rank"]
            # Built-ins are marked as such so they can't be deleted later.
            self.is_system = True
        elif not self.label:
            self.label = self.key.replace("_", " ").title()
        super().save(*args, **kwargs)

    def has(self, capability: str) -> bool:
        return capability in (self.capabilities or [])


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
