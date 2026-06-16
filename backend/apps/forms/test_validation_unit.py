import pytest
from rest_framework.exceptions import ValidationError

from apps.forms.validation import validate_submission


def test_validate_submission_accepts_valid_payload():
    schema = {
        "fields": [
            {"name": "claim_value", "type": "number", "required": True, "min": 0, "max": 10000},
            {"name": "description", "type": "textarea", "required": True},
            {"name": "category", "type": "dropdown", "required": True},
            {"name": "urgent", "type": "checkbox", "required": False},
        ]
    }
    data = {
        "claim_value": 1250,
        "description": "Burst pipe claim",
        "category": "Property",
        "urgent": True,
    }

    validate_submission(schema, data)


@pytest.mark.parametrize(
    ("schema", "data", "error_key"),
    [
        (
            {"fields": [{"name": "description", "type": "text", "required": True}]},
            {},
            "description",
        ),
        (
            {"fields": [{"name": "claim_value", "type": "number", "required": True}]},
            {"claim_value": "not-a-number"},
            "claim_value",
        ),
        (
            {"fields": [{"name": "claim_value", "type": "number", "required": True, "min": 10}]},
            {"claim_value": 5},
            "claim_value",
        ),
        (
            {"fields": [{"name": "urgent", "type": "checkbox", "required": True}]},
            {"urgent": "yes"},
            "urgent",
        ),
    ],
)
def test_validate_submission_rejects_invalid_payload(schema, data, error_key):
    with pytest.raises(ValidationError) as exc:
        validate_submission(schema, data)

    assert error_key in exc.value.detail
