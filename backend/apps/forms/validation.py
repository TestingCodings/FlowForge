from rest_framework.exceptions import ValidationError


def _validate_type(value, field_type):
    if field_type in {"text", "textarea", "dropdown"} and not isinstance(value, str):
        raise ValidationError("must be a string")
    if field_type in {"number", "currency"} and not isinstance(value, (int, float)):
        raise ValidationError("must be a number")
    if field_type in {"checkbox", "toggle"} and not isinstance(value, bool):
        raise ValidationError("must be a boolean")
    if field_type in {"date", "datetime"} and not isinstance(value, str):
        raise ValidationError("must be an ISO string")


def validate_submission(schema, data):
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

            if field_type in {"number", "currency"}:
                minimum = field.get("min")
                maximum = field.get("max")
                if minimum is not None and value < minimum:
                    errors[name] = f"must be >= {minimum}"
                if maximum is not None and value > maximum:
                    errors[name] = f"must be <= {maximum}"

    if errors:
        raise ValidationError(errors)
