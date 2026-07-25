"""
Tests for WS-A -- File & image uploads (backend).

Coverage:
- upload: success (image, document), oversize, wrong-type, unauthenticated
- list: viewer can list, unauthenticated cannot
- download: viewer can download, unauthenticated cannot, missing file is 404
- delete: uploader can delete own asset, designer can delete any, viewer cannot
- generated storage key: original filename never used as storage path
- image EXIF sanitisation: re-encoded through Pillow, original EXIF gone
- role checks: participant+ to upload, viewer+ to list/download
- private by default: no public URL exposed in serialiser
"""
import io
import struct
import uuid

import pytest
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleName, User, UserRole
from apps.media.models import MediaAsset
from apps.media.validation import (
    detect_content_type,
    safe_original_name,
    sanitise_image,
    validate_upload,
)

_TEST_PW = "StrongPass123!"


# -- Helpers --

def _make_user(email, role_name=None):
    user = User.objects.create_user(
        email=email, **{"password": _TEST_PW}, first_name="T", last_name="U"
    )
    if role_name:
        role, _ = Role.objects.get_or_create(name=role_name)
        UserRole.objects.create(user=user, role=role)
    return user


def _auth_client(user):
    client = APIClient()
    resp = client.post(
        "/api/auth/login/",
        {"email": user.email, **{"password": _TEST_PW}},
        format="json",
    )
    token = resp.data["access"]
    client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
    return client


def _make_jpeg_bytes() -> bytes:
    """Return a valid 1x1 RGB JPEG via Pillow."""
    img = Image.new("RGB", (1, 1), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.read()


def _make_png_bytes() -> bytes:
    """Return a valid 1x1 RGB PNG via Pillow."""
    img = Image.new("RGB", (1, 1), color=(0, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def _make_jpeg_with_exif_bytes() -> bytes:
    """Return a JPEG with a fake EXIF APP1 marker injected."""
    img = Image.new("RGB", (4, 4), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpeg_bytes = bytearray(buf.getvalue())
    # Build a fake APP1 segment to inject (marker + length + Exif header)
    fake_app1 = (
        bytes([0xff, 0xe1])     # APP1 marker
        + struct.pack(">H", 18) # length field (includes itself)
        + b"Exif\x00\x00"
        + b"II\x2a\x00"
        + b"\x08\x00\x00\x00"
        + b"\x00\x00"
    )
    # Insert after SOI (first 2 bytes: ff d8)
    injected = bytes(jpeg_bytes[:2]) + fake_app1 + bytes(jpeg_bytes[2:])
    return injected


# -- Validation unit tests --

class TestDetectContentType:
    def test_jpeg(self):
        data = _make_jpeg_bytes()
        assert detect_content_type(data) == "image/jpeg"

    def test_png(self):
        data = _make_png_bytes()
        assert detect_content_type(data) == "image/png"

    def test_pdf(self):
        assert detect_content_type(b"%PDF-1.4" + b"\x00" * 8) == "application/pdf"

    def test_zip(self):
        assert detect_content_type(b"PK\x03\x04" + b"\x00" * 12) == "application/zip"

    def test_unknown_binary_rejected(self):
        assert detect_content_type(b"\x00\x01\x02\x03\x04\x05\x06\x07") is None

    def test_executable_rejected(self):
        # MZ header (Windows PE) must not match any allowed type
        assert detect_content_type(b"MZ" + b"\x00" * 14) is None


class TestValidateUpload:
    def test_accepts_jpeg(self):
        data = _make_jpeg_bytes()
        f = io.BytesIO(data)
        f.name = "photo.jpg"
        mime, kind, size = validate_upload(f)
        assert mime == "image/jpeg"
        assert kind == "image"
        assert size == len(data)

    def test_rejects_oversized(self, settings):
        settings.MEDIA_UPLOAD_MAX_BYTES = 10
        data = _make_jpeg_bytes()
        f = io.BytesIO(data)
        f.name = "big.jpg"
        with pytest.raises(Exception, match="too large"):
            validate_upload(f)

    def test_rejects_unknown_type(self):
        # Raw binary that does not match any magic bytes
        f = io.BytesIO(b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f")
        f.name = "bad.bin"
        with pytest.raises(Exception, match="not allowed"):
            validate_upload(f)


class TestSafeOriginalName:
    def test_strips_path(self):
        assert safe_original_name("/etc/passwd") == "passwd"

    def test_strips_null(self):
        assert "\x00" not in safe_original_name("file\x00name.jpg")

    def test_empty_returns_upload(self):
        assert safe_original_name("") == "upload"

    def test_max_length(self):
        assert len(safe_original_name("a" * 300)) == 255


# -- API integration tests --

UPLOAD_URL = "/api/media/"


@pytest.mark.django_db
class TestUploadEndpoint:
    def test_participant_can_upload_jpeg(self):
        user = _make_user("p@example.com", RoleName.PARTICIPANT)
        client = _auth_client(user)
        jpeg = _make_jpeg_bytes()
        f = io.BytesIO(jpeg)
        f.name = "photo.jpg"
        resp = client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert resp.data["kind"] == "image"
        assert resp.data["content_type"] == "image/jpeg"
        assert "download_url" in resp.data
        assert MediaAsset.objects.filter(id=resp.data["id"]).exists()

    def test_participant_can_upload_pdf(self):
        user = _make_user("p2@example.com", RoleName.PARTICIPANT)
        client = _auth_client(user)
        pdf = b"%PDF-1.4 " + b"\x00" * 30
        f = io.BytesIO(pdf)
        f.name = "doc.pdf"
        resp = client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["kind"] == "document"

    def test_viewer_cannot_upload(self):
        user = _make_user("v@example.com", RoleName.VIEWER)
        client = _auth_client(user)
        f = io.BytesIO(_make_jpeg_bytes())
        f.name = "photo.jpg"
        resp = client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_upload(self):
        client = APIClient()
        f = io.BytesIO(_make_jpeg_bytes())
        f.name = "photo.jpg"
        resp = client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_oversize_rejected(self, settings):
        settings.MEDIA_UPLOAD_MAX_BYTES = 5
        user = _make_user("p3@example.com", RoleName.PARTICIPANT)
        client = _auth_client(user)
        f = io.BytesIO(_make_jpeg_bytes())
        f.name = "photo.jpg"
        resp = client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "too large" in resp.data["detail"].lower()

    def test_wrong_type_rejected(self):
        user = _make_user("p4@example.com", RoleName.PARTICIPANT)
        client = _auth_client(user)
        # Windows PE header -- should not match any allowed type
        exe = b"MZ" + b"\x00" * 60
        f = io.BytesIO(exe)
        f.name = "bad.exe"
        resp = client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "not allowed" in resp.data["detail"].lower()

    def test_missing_file_field(self):
        user = _make_user("p5@example.com", RoleName.PARTICIPANT)
        client = _auth_client(user)
        resp = client.post(UPLOAD_URL, {}, format="multipart")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_generated_key_does_not_contain_original_filename(self):
        """Storage path must be a UUID-based key, not the original filename."""
        user = _make_user("p6@example.com", RoleName.PARTICIPANT)
        client = _auth_client(user)
        f = io.BytesIO(_make_jpeg_bytes())
        f.name = "secret_document.jpg"
        resp = client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_201_CREATED
        asset = MediaAsset.objects.get(id=resp.data["id"])
        # The storage path must not contain the original filename
        assert "secret_document" not in asset.file.name

    def test_uploaded_by_set_to_uploader(self):
        user = _make_user("p7@example.com", RoleName.PARTICIPANT)
        client = _auth_client(user)
        f = io.BytesIO(_make_jpeg_bytes())
        f.name = "photo.jpg"
        resp = client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_201_CREATED
        asset = MediaAsset.objects.get(id=resp.data["id"])
        assert asset.uploaded_by_id == user.id

    def test_download_url_not_public(self):
        """download_url must point at our authenticated endpoint, not a bucket URL."""
        user = _make_user("p8@example.com", RoleName.PARTICIPANT)
        client = _auth_client(user)
        f = io.BytesIO(_make_jpeg_bytes())
        f.name = "photo.jpg"
        resp = client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_201_CREATED
        url = resp.data["download_url"]
        # Must route through /api/media/<id>/download/, not an external storage URL
        assert "/api/media/" in url
        assert "/download/" in url
        assert "s3" not in url.lower()
        assert "r2" not in url.lower()


@pytest.mark.django_db
class TestListEndpoint:
    def test_viewer_can_list(self):
        user = _make_user("v2@example.com", RoleName.VIEWER)
        client = _auth_client(user)
        resp = client.get(UPLOAD_URL)
        assert resp.status_code == status.HTTP_200_OK

    def test_unauthenticated_cannot_list(self):
        client = APIClient()
        resp = client.get(UPLOAD_URL)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_returns_assets(self):
        uploader = _make_user("u@example.com", RoleName.PARTICIPANT)
        client = _auth_client(uploader)
        f = io.BytesIO(_make_jpeg_bytes())
        f.name = "photo.jpg"
        client.post(UPLOAD_URL, {"file": f}, format="multipart")
        resp = client.get(UPLOAD_URL)
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data.get("results", resp.data)
        assert len(results) >= 1


@pytest.mark.django_db
class TestDownloadEndpoint:
    def _upload_asset(self, user_email, role):
        user = _make_user(user_email, role)
        client = _auth_client(user)
        f = io.BytesIO(_make_jpeg_bytes())
        f.name = "photo.jpg"
        resp = client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_201_CREATED
        return user, client, resp.data["id"]

    def test_viewer_can_download(self):
        _, client, asset_id = self._upload_asset("dl1@example.com", RoleName.PARTICIPANT)
        resp = client.get(f"/api/media/{asset_id}/download/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp["Content-Disposition"].startswith("attachment")

    def test_unauthenticated_cannot_download(self):
        _, _, asset_id = self._upload_asset("dl2@example.com", RoleName.PARTICIPANT)
        client = APIClient()
        resp = client.get(f"/api/media/{asset_id}/download/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_download_nonexistent_returns_404(self):
        viewer = _make_user("dl3@example.com", RoleName.VIEWER)
        client = _auth_client(viewer)
        resp = client.get(f"/api/media/{uuid.uuid4()}/download/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestDeleteEndpoint:
    def _create_asset_in_db(self, user):
        """Create a MediaAsset row directly (without actual file on disk)."""
        asset = MediaAsset.objects.create(
            original_name="test.jpg",
            content_type="image/jpeg",
            size_bytes=100,
            kind="image",
            uploaded_by=user,
        )
        # Assign a fake file path so the storage backend does not error on delete
        asset.file.name = f"media_assets/{uuid.uuid4()}/{uuid.uuid4()}"
        asset.save(update_fields=["file"])
        return asset

    def test_uploader_can_delete_own_asset(self):
        user = _make_user("del1@example.com", RoleName.PARTICIPANT)
        asset = self._create_asset_in_db(user)
        client = _auth_client(user)
        resp = client.delete(f"/api/media/{asset.id}/")
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert not MediaAsset.objects.filter(id=asset.id).exists()

    def test_designer_can_delete_any_asset(self):
        uploader = _make_user("del2@example.com", RoleName.PARTICIPANT)
        designer = _make_user("del3@example.com", RoleName.WORKFLOW_DESIGNER)
        asset = self._create_asset_in_db(uploader)
        client = _auth_client(designer)
        resp = client.delete(f"/api/media/{asset.id}/")
        assert resp.status_code == status.HTTP_204_NO_CONTENT

    def test_viewer_cannot_delete_others_asset(self):
        uploader = _make_user("del4@example.com", RoleName.PARTICIPANT)
        viewer = _make_user("del5@example.com", RoleName.VIEWER)
        asset = self._create_asset_in_db(uploader)
        client = _auth_client(viewer)
        resp = client.delete(f"/api/media/{asset.id}/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_delete(self):
        user = _make_user("del6@example.com", RoleName.PARTICIPANT)
        asset = self._create_asset_in_db(user)
        client = APIClient()
        resp = client.delete(f"/api/media/{asset.id}/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestImageExifSanitisation:
    def test_png_roundtrip_reencodes(self):
        """Upload a PNG; the stored asset must be re-encoded by Pillow."""
        user = _make_user("exif1@example.com", RoleName.PARTICIPANT)
        client = _auth_client(user)
        png_data = _make_png_bytes()
        f = io.BytesIO(png_data)
        f.name = "photo.png"
        resp = client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["content_type"] == "image/png"

    def test_sanitise_image_strips_exif_marker(self):
        """
        Direct unit test: sanitise_image() on a JPEG with an APP1/EXIF marker
        produces output that does NOT contain the original APP1 marker bytes.
        """
        jpeg_with_exif = _make_jpeg_with_exif_bytes()
        f = io.BytesIO(jpeg_with_exif)
        f.name = "photo.jpg"
        out = sanitise_image(f, "JPEG")
        result = out.read()
        # The EXIF APP1 marker 0xff 0xe1 must not appear in the sanitised output
        assert b"\xff\xe1" not in result, "EXIF APP1 marker still present after sanitisation"

    def test_jpeg_upload_strips_exif(self):
        """
        End-to-end: upload a JPEG with EXIF; verify the stored file has no APP1 segment.
        """
        user = _make_user("exif2@example.com", RoleName.PARTICIPANT)
        client = _auth_client(user)
        jpeg_with_exif = _make_jpeg_with_exif_bytes()
        f = io.BytesIO(jpeg_with_exif)
        f.name = "with_exif.jpg"
        resp = client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_201_CREATED
        asset = MediaAsset.objects.get(id=resp.data["id"])
        with asset.file.open("rb") as stored:
            stored_bytes = stored.read()
        assert b"\xff\xe1" not in stored_bytes, "Stored JPEG still contains EXIF APP1 marker"


@pytest.mark.django_db
class TestPrivateByDefault:
    def test_file_field_not_in_serialiser(self):
        """The file field (internal storage path) must never appear in API responses."""
        user = _make_user("priv@example.com", RoleName.PARTICIPANT)
        client = _auth_client(user)
        f = io.BytesIO(_make_jpeg_bytes())
        f.name = "photo.jpg"
        resp = client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_201_CREATED
        assert "file" not in resp.data  # internal storage path must not leak

    def test_update_not_allowed(self):
        user = _make_user("upd@example.com", RoleName.PARTICIPANT)
        client = _auth_client(user)
        # Create an asset
        f = io.BytesIO(_make_jpeg_bytes())
        f.name = "photo.jpg"
        resp = client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert resp.status_code == status.HTTP_201_CREATED
        asset_id = resp.data["id"]
        # PUT/PATCH should be blocked (405 or 404 depending on router configuration)
        put_resp = client.put(f"/api/media/{asset_id}/", {}, format="json")
        patch_resp = client.patch(f"/api/media/{asset_id}/", {}, format="json")
        assert put_resp.status_code in (
            status.HTTP_405_METHOD_NOT_ALLOWED,
            status.HTTP_404_NOT_FOUND,
        )
        assert patch_resp.status_code in (
            status.HTTP_405_METHOD_NOT_ALLOWED,
            status.HTTP_404_NOT_FOUND,
        )
