import uuid

from django.conf import settings
from django.db import models

from apps.workflows.models import WorkflowDefinition

from .crypto import decrypt, encrypt


class Secret(models.Model):
    """
    An encrypted credential referenced by action hooks as {{secret.NAME}}.

    The plaintext value is never stored in a column, never returned by the API,
    and only decrypted in the worker at hook-fire time. See docs/HOOKS.md.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.SlugField(max_length=100)
    # Workflow-scoped, or workspace-global when null.
    scope = models.ForeignKey(
        WorkflowDefinition, on_delete=models.CASCADE, null=True, blank=True, related_name="secrets"
    )
    ciphertext = models.BinaryField()
    key_version = models.PositiveSmallIntegerField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_secrets",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "secret"
        ordering = ["scope_id", "name"]
        constraints = [
            models.UniqueConstraint(fields=["scope", "name"], name="unique_secret_name_per_scope"),
        ]

    def __str__(self):
        return f"{self.name}{'' if self.scope_id is None else f' @{self.scope_id}'}"

    def set_value(self, plaintext: str) -> None:
        """Encrypt and store a new value under the current key version."""
        self.ciphertext, self.key_version = encrypt(plaintext)

    def reveal(self) -> str:
        """Decrypt the value. Worker-only — never call this in a request path
        that could serialise the result back to a client."""
        return decrypt(self.ciphertext, self.key_version)

    @classmethod
    def resolve(cls, name: str, workflow_definition_id=None) -> "Secret | None":
        """Workflow-scoped secret wins over a workspace-global one of the same name."""
        if workflow_definition_id is not None:
            scoped = cls.objects.filter(name=name, scope_id=workflow_definition_id).first()
            if scoped:
                return scoped
        return cls.objects.filter(name=name, scope__isnull=True).first()
