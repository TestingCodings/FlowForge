from django.contrib import admin

from .models import Secret


@admin.register(Secret)
class SecretAdmin(admin.ModelAdmin):
    """Values are never shown — only names and metadata (docs/HOOKS.md)."""
    list_display = ("name", "scope", "key_version", "created_by", "created_at", "last_used_at")
    list_filter = ("scope", "key_version")
    search_fields = ("name",)
    readonly_fields = ("id", "key_version", "created_at", "updated_at", "last_used_at")
    # ciphertext deliberately excluded from the form — no plaintext, no raw bytes.
    exclude = ("ciphertext",)

    def has_change_permission(self, request, obj=None):
        return False  # rotate via the API; never edit ciphertext by hand
