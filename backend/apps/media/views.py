from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.base import ContentFile
from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsViewer, has_capability, require_capability

from .models import MediaAsset
from .serializers import MediaAssetSerializer
from .validation import image_format_for, safe_original_name, sanitise_image, validate_upload


class MediaAssetViewSet(viewsets.ModelViewSet):
    """
    Media uploads (docs/MEDIA.md Part 1).

    * `POST   /api/media/`                 multipart upload — participant+
    * `GET    /api/media/`                 list — viewer+
    * `GET    /api/media/<id>/download/`   authenticated download — viewer+
    * `DELETE /api/media/<id>/`            uploader, or workflow_designer+

    Assets are immutable: there is no update route (rotate by re-uploading).
    """

    queryset = MediaAsset.objects.select_related("uploaded_by", "workflow_instance").all()
    serializer_class = MediaAssetSerializer
    permission_classes = [IsAuthenticated, IsViewer]
    parser_classes = [MultiPartParser, FormParser]
    filterset_fields = ["workflow_instance", "workflow_definition", "kind"]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def create(self, request, *args, **kwargs):
        require_capability(request.user, "media.upload", action="upload a file")

        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "A file is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            mime, kind, size = validate_upload(upload)
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=status.HTTP_400_BAD_REQUEST)

        # Images are re-encoded so EXIF and any smuggled trailing payload are
        # dropped before the bytes ever reach storage.
        image_format = image_format_for(mime)
        if image_format:
            cleaned = sanitise_image(upload, image_format)
            payload = cleaned.read()
        else:
            upload.seek(0)
            payload = upload.read()

        asset = MediaAsset(
            original_name=safe_original_name(getattr(upload, "name", "")),
            content_type=mime,
            size_bytes=len(payload),
            kind=kind,
            uploaded_by=request.user,
            workflow_instance_id=request.data.get("workflow_instance") or None,
            workflow_definition_id=request.data.get("workflow_definition") or None,
        )
        # save=False then save(): upload_to needs the pk and content_type, both
        # of which are set on the unsaved instance above.
        asset.file.save(f"{asset.id}", ContentFile(payload), save=False)
        asset.save()

        serializer = self.get_serializer(asset)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        """Stream the file to an authorised user. Assets are never public."""
        asset = self.get_object()
        try:
            handle = asset.file.open("rb")
        except (FileNotFoundError, ValueError):
            return Response({"detail": "File is no longer available."}, status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(handle, content_type=asset.content_type)
        response["Content-Disposition"] = f'attachment; filename="{asset.original_name}"'
        return response

    def destroy(self, request, *args, **kwargs):
        asset = self.get_object()
        is_uploader = asset.uploaded_by_id == request.user.id
        if not (is_uploader or has_capability(request.user, "media.delete")):
            raise PermissionDenied("You can only delete assets you uploaded.")
        # Best-effort storage cleanup: a missing file must not block the row
        # being removed.
        try:
            asset.file.delete(save=False)
        except Exception:
            pass
        asset.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
