"""`file` / `image` form fields hold a MediaAsset reference (docs/MEDIA.md).

Before this, both types existed in the frontend but not in backend
validation, so they fell through `_validate_type` unchecked — any string was
accepted and the "evidence" on a test result could be a typo, a dead URL, or
a pointer to someone else's attachment.
"""
import io
import uuid

import pytest
from rest_framework.exceptions import ValidationError

from apps.forms.validation import validate_submission


SCHEMA = {"fields": [{"name": "evidence", "type": "file", "required": False}]}
IMAGE_SCHEMA = {"fields": [{"name": "screenshot", "type": "image", "required": False}]}


# ── Shape validation (no DB) ───────────────────────────────────────────────

def test_accepts_a_uuid_string():
    validate_submission(SCHEMA, {"evidence": str(uuid.uuid4())})


def test_rejects_a_non_uuid_string():
    """A pasted URL or filename is the mistake this prevents."""
    with pytest.raises(ValidationError) as exc:
        validate_submission(SCHEMA, {"evidence": "https://example.com/screenshot.png"})
    assert "evidence" in exc.value.detail


def test_rejects_a_non_string():
    with pytest.raises(ValidationError):
        validate_submission(SCHEMA, {"evidence": 12345})


def test_image_type_is_validated_the_same_way():
    with pytest.raises(ValidationError):
        validate_submission(IMAGE_SCHEMA, {"screenshot": "not-a-uuid"})


def test_optional_file_may_be_omitted():
    validate_submission(SCHEMA, {})


def test_required_file_must_be_present():
    schema = {"fields": [{"name": "evidence", "type": "file", "required": True}]}
    with pytest.raises(ValidationError) as exc:
        validate_submission(schema, {})
    assert "required" in str(exc.value.detail["evidence"]).lower()


# ── Existence + ownership (needs the DB) ───────────────────────────────────

def _png_upload():
    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, format="PNG")
    return SimpleUploadedFile("shot.png", buf.getvalue(), content_type="image/png")


@pytest.fixture
def asset_setup(db):
    from apps.media.models import MediaAsset
    from tests.factories import (
        StateFactory, UserFactory, WorkflowDefinitionFactory, WorkflowInstanceFactory,
    )

    wf = WorkflowDefinitionFactory()
    StateFactory(workflow_definition=wf, name="Open", is_initial=True, position_order=1)
    user = UserFactory()
    mine = WorkflowInstanceFactory(workflow_definition=wf)
    theirs = WorkflowInstanceFactory(workflow_definition=wf)

    asset = MediaAsset.objects.create(
        workflow_instance=mine, file=_png_upload(), original_name="shot.png",
        content_type="image/png", size_bytes=100, uploaded_by=user,
    )
    return mine, theirs, asset


@pytest.mark.django_db
class TestAssetExistenceAndOwnership:
    def test_accepts_an_asset_attached_to_this_instance(self, asset_setup):
        mine, _theirs, asset = asset_setup
        validate_submission(SCHEMA, {"evidence": str(asset.id)}, instance=mine)

    def test_rejects_an_asset_that_does_not_exist(self, asset_setup):
        mine, _theirs, _asset = asset_setup
        with pytest.raises(ValidationError) as exc:
            validate_submission(SCHEMA, {"evidence": str(uuid.uuid4())}, instance=mine)
        assert "not found" in str(exc.value.detail["evidence"]).lower()

    def test_rejects_an_asset_belonging_to_another_instance(self, asset_setup):
        """Otherwise a form submission is a way to reference — and through the
        UI, view — an attachment from an instance you may not be able to see."""
        _mine, theirs, asset = asset_setup
        with pytest.raises(ValidationError) as exc:
            validate_submission(SCHEMA, {"evidence": str(asset.id)}, instance=theirs)
        assert "evidence" in exc.value.detail

    def test_shape_only_validation_when_no_instance_context(self, asset_setup):
        """validate_submission is also called without an instance (e.g. schema
        preview); it must still check shape and must not crash."""
        _mine, _theirs, asset = asset_setup
        validate_submission(SCHEMA, {"evidence": str(asset.id)})
