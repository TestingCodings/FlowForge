from rest_framework import serializers

from .models import MediaAsset


class MediaAssetSerializer(serializers.ModelSerializer):
    """Read serialiser. Deliberately omits `file`: the internal storage path
    must never leak, and downloads go through the authenticated endpoint."""

    download_url = serializers.SerializerMethodField()
    uploaded_by_email = serializers.CharField(source="uploaded_by.email", read_only=True, default=None)

    class Meta:
        model = MediaAsset
        fields = (
            "id", "original_name", "content_type", "size_bytes", "kind",
            "workflow_instance", "workflow_definition",
            "uploaded_by", "uploaded_by_email", "created_at", "download_url",
        )
        read_only_fields = fields

    def get_download_url(self, obj) -> str:
        path = f"/api/media/{obj.id}/download/"
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request else path
