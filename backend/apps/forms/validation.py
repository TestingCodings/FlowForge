import uuid

from rest_framework.exceptions import ValidationError

# Every field type the platform understands. Keep in sync with FormField in
# frontend/src/types/api.ts and FIELD_TYPES in the form editor — a type that
# validates here but isn't offered there is a capability nobody can reach.
FILE_TYPES = {"file", "image"}
FIELD_TYPES = {
    "text", "textarea", "dropdown",
    "number", "currency",
    "checkbox", "toggle",
    "date", "datetime",
    *FILE_TYPES,
}


def _validate_type(value, field_type):
    if field_type in {"text", "textarea", "dropdown"} and not isinstance(value, str):
        raise ValidationError("must be a string")
    if field_type in {"number", "currency"} and not isinstance(value, (int, float)):
        raise ValidationError("must be a number")
    if field_type in {"checkbox", "toggle"} and not isinstance(value, bool):
        raise ValidationError("must be a boolean")
    if field_type in {"date", "datetime"} and not isinstance(value, str):
        raise ValidationError("must be an ISO string")
    if field_type in FILE_TYPES:
        # A file field holds a MediaAsset id, not a URL or a filename. Storing
        # a reference (rather than a link someone pasted) is what makes the
        # attachment durable, access-controlled, and actually present.
        if not isinstance(value, str):
            raise ValidationError("must be a media asset id")
        try:
            uuid.UUID(value)
        except (ValueError, AttributeError, TypeError):
            raise ValidationError(
                "must be a media asset id — upload the file, don't paste a link"
            )


def _validate_asset_reference(value, instance):
    """Check a file field's asset exists and belongs to this instance.

    Shape alone isn't enough: a well-formed UUID can point at nothing, or at
    an attachment on an instance the submitter can't otherwise see. Requiring
    the asset to be anchored to this instance (or to its workflow definition,
    for reusable assets) keeps a form submission from becoming a way to
    reference someone else's file.
    """
    from apps.media.models import MediaAsset

    asset = MediaAsset.objects.filter(id=value).first()
    if asset is None:
        raise ValidationError("media asset not found")

    belongs = (
        asset.workflow_instance_id == instance.id
        or asset.workflow_definition_id == instance.workflow_definition_id
    )
    if not belongs:
        raise ValidationError("media asset does not belong to this instance")


def validate_submission(schema, data, instance=None):
    """Validate submitted values against a form schema.

    `instance` is optional so the function stays usable for schema-only
    checks (previews, tests). When it is supplied, file fields additionally
    have their asset resolved and ownership-checked.
    """
    if not isinstance(schema, dict):
        raise ValidationError("schema must be an object")
    if not isinstance(data, dict):
        raise ValidationError("data must be an object")

    fields = schema.get("fields", [])
    errors = {}

    for field in fields:
        name = field.get("name")
        field_type = field.get("type", "text")
        required = field.get("required", False)

        if not name:
            continue

        present = name in data and data.get(name) is not None
        if required and not present:
            errors[name] = "This field is required."
            continue

        if present:
            value = data.get(name)
            try:
                _validate_type(value, field_type)
            except ValidationError as exc:
                errors[name] = str(exc.detail[0]) if hasattr(exc, "detail") else str(exc)
                continue

            if field_type in FILE_TYPES and instance is not None:
                try:
                    _validate_asset_reference(value, instance)
                except ValidationError as exc:
                    errors[name] = str(exc.detail[0]) if hasattr(exc, "detail") else str(exc)
                    continue

            if field_type in {"number", "currency"}:
                minimum = field.get("min")
                maximum = field.get("max")
                if minimum is not None and value < minimum:
                    errors[name] = f"must be >= {minimum}"
                if maximum is not None and value > maximum:
                    errors[name] = f"must be <= {maximum}"

    if errors:
        raise ValidationError(errors)
