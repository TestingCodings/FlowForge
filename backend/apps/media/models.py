import uuid

from django.conf import settings
from django.db import models

from apps.instances.models import WorkflowInstance
from apps.workflows.models import WorkflowDefinition


def asset_upload_path(instance, filename):
    """Generate the storage key.

    Deliberately ignores the client-supplied filename: the key is derived from
    UUIDs plus an extension inferred from the *sniffed* MIME type, so a crafted
    name can never influence where the file lands (docs/MEDIA.md).
    """
    from .validation import extension_for

    return f"media_assets/{instance.id}/{uuid.uuid4().hex}{extension_for(instance.content_type)}"


class MediaAsset(models.Model):
    """An uploaded file owned by FlowForge (docs/MEDIA.md Part 1).

    Private by default: the storage path is never serialised, and downloads go
    through an authenticated endpoint rather than a public bucket URL.
    """

    class Kind(models.TextChoices):
        IMAGE = "image", "Image"
        DOCUMENT = "document", "Document"
        AUDIO = "audio", "Audio"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Optional anchors: an instance attachment, or a workflow-level asset
    # (e.g. a reusable background for the scene shell).
    workflow_instance = models.ForeignKey(
        WorkflowInstance, on_delete=models.CASCADE, null=True, blank=True, related_name="assets",
    )
    workflow_definition = models.ForeignKey(
        WorkflowDefinition, on_delete=models.CASCADE, null=True, blank=True, related_name="assets",
    )
    file = models.FileField(upload_to=asset_upload_path, max_length=500)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveBigIntegerField(default=0)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="uploaded_assets",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "media_asset"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.original_name} ({self.content_type})"
