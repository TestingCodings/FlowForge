from django.contrib import admin

from .models import MediaAsset


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ("original_name", "kind", "content_type", "size_bytes", "uploaded_by", "created_at")
    list_filter = ("kind", "content_type")
    search_fields = ("original_name",)
    readonly_fields = ("id", "file", "content_type", "size_bytes", "kind", "created_at")
