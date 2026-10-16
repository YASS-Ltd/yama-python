import pytest
from jsonschema.exceptions import ValidationError

from tests.schema import validate

ACCESS_CODE = {
    "uuid": "6f1c2a0e-8a4b-4c1e-9a43-2b7d1f0e9c11",
    "unit": "dd1053d5-0a4b-4c0d-a619-6a1457d97de6",
    "code": "4321",
    "name": "Cleaner",
    "expires_at": None,
}


def test_schema_accepts_a_valid_access_code() -> None:
    validate("AccessCode", ACCESS_CODE)


def test_schema_rejects_a_misnamed_field() -> None:
    bad = {k: v for k, v in ACCESS_CODE.items() if k != "expires_at"} | {"expiry": None}
    with pytest.raises(ValidationError, match="expiry"):
        validate("AccessCode", bad)


def test_schema_rejects_a_wrong_type() -> None:
    with pytest.raises(ValidationError):
        validate("AccessCode", ACCESS_CODE | {"code": 4321})
