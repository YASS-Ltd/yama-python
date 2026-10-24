from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

from tests.schema import schema_component, validate
from yama.models import (
    AccessCode,
    AccessCodeCreate,
    AccessCodeUpdate,
    AccessLevel,
    ApiKeyDetails,
    Building,
    CallLogEntry,
    CallResult,
    CallStepKind,
    CodeAttemptResult,
    Contact,
    DialStatus,
    DoorDigit,
    Unit,
    UnitAccessType,
)

UNIT = "dd1053d5-0a4b-4c0d-a619-6a1457d97de6"
BUILDING = "5f0c3b8e-8a52-4a38-9f57-1d2b6c0e4a11"
NULL_STEP = dict.fromkeys(
    ("attempt_result", "entered_digits", "code_name", "contact_name", "dial_status")
)
CALL = {
    "uuid": "0c9c3da7-30bd-4be3-b810-bb639d439e1d",
    "unit": UNIT,
    "building": BUILDING,
    "reference": "7DCD03",
    "started_at": "2026-10-10T22:09:11.312885Z",
    "duration_seconds": 11,
    "result": "code_not_accepted",
    "result_label": "Wrong or expired code",
    "summary": "5678 · Expired code",
    "imported": False,
    "steps": [
        {"kind": "received", "at": "2026-10-10T22:09:11Z", "text": "Call started", **NULL_STEP},
        {
            **NULL_STEP,
            "kind": "input",
            "at": "2026-10-10T22:09:11Z",
            "text": "Code entered: 5678 · Expired",
            "attempt_result": "expired",
            "entered_digits": "5678",
        },
        {
            **NULL_STEP,
            "kind": "dial_ended",
            "at": "2026-10-10T22:09:12Z",
            "text": "No answer",
            "dial_status": "no-answer",
        },
    ],
}
SAMPLES: list[tuple[type[BaseModel], str, dict[str, Any]]] = [
    (
        ApiKeyDetails,
        "ApiKey",
        {
            "uuid": "d6aa1973-6516-4035-8e52-b4d932c6e407",
            "name": "Doorbell",
            "created_at": "2026-10-14T20:23:57.294919Z",
            "expires_at": "2026-11-13T20:23:57.294442Z",
            "last_used_at": "2026-10-14T20:24:28.772111Z",
            "permissions": {
                "codes": "write",
                "contacts": "none",
                "call_log": "read",
                "buildings": "read",
            },
            "scopes": ["buildings:read", "codes:write"],
            "unit_access": {"type": "buildings", "buildings": [BUILDING], "units": []},
        },
    ),
    (
        Building,
        "Building",
        {
            "uuid": BUILDING,
            "name": "Example Tower",
            "address": "1 Example St",
            "caller_id": "+16045550123",
            "unit_count": 11,
        },
    ),
    (
        Unit,
        "Unit",
        {
            "uuid": UNIT,
            "building": BUILDING,
            "name": "Unit 101",
            "door_digit": "9",
            "dial_in_number": None,
        },
    ),
    (
        Contact,
        "Contact",
        {
            "uuid": "1dc19ab9-2785-4999-930a-0096ce94c485",
            "unit": UNIT,
            "number": "+16045550111",
            "menu_digit": "1",
            "name": "Concierge",
        },
    ),
    (
        AccessCode,
        "AccessCode",
        {
            "uuid": "1dc19ab9-2785-4999-930a-0096ce94c485",
            "unit": UNIT,
            "code": "482915",
            "name": "Dog walker",
            "expires_at": "2026-11-01T00:00:00Z",
        },
    ),
    (CallLogEntry, "CallLogEntry", CALL),
]


@pytest.mark.parametrize(("model", "component", "data"), SAMPLES)
def test_mod_1_parses_every_response_model(
    model: type[BaseModel], component: str, data: dict[str, Any]
) -> None:
    validate(component, data)  # the sample is a valid response
    parsed = model.model_validate(data)
    assert isinstance(parsed.uuid, UUID)  # type: ignore[attr-defined]
    assert set(model.model_fields) == set(data), "the model mirrors the schema field for field"
    assert parsed.model_dump(mode="json", exclude_unset=True).keys() == data.keys()


def test_mod_1_uses_uuids_and_aware_datetimes() -> None:
    call = CallLogEntry.model_validate(CALL)
    assert call.unit == UUID(UNIT)
    assert call.started_at == datetime(2026, 10, 10, 22, 9, 11, 312885, tzinfo=timezone.utc)
    assert all(step.at.tzinfo is not None for step in call.steps)
    key = ApiKeyDetails.model_validate(SAMPLES[0][2] | {"expires_at": None})
    assert key.expires_at is None
    assert key.unit_access.buildings == [UUID(BUILDING)]


def test_mod_1_response_models_are_frozen() -> None:
    code = AccessCode.model_validate(SAMPLES[4][2])
    with pytest.raises(ValidationError):
        code.name = "changed"  # type: ignore[misc]


def test_mod_2_keeps_unknown_response_fields_readable() -> None:
    code = AccessCode.model_validate({**SAMPLES[4][2], "colour": "red"})
    assert code.colour == "red"  # type: ignore[attr-defined]
    assert code.model_extra == {"colour": "red"}


def test_mod_3_returns_known_enum_values_as_enums() -> None:
    call = CallLogEntry.model_validate(CALL)
    assert call.result is CallResult.CODE_NOT_ACCEPTED
    assert call.steps[1].kind is CallStepKind.INPUT
    assert call.steps[1].attempt_result is CodeAttemptResult.EXPIRED
    assert call.steps[2].dial_status is DialStatus.NO_ANSWER
    assert call.steps[0].attempt_result is None
    assert Unit.model_validate(SAMPLES[2][2]).door_digit is DoorDigit.NINE
    key = ApiKeyDetails.model_validate(SAMPLES[0][2])
    assert key.permissions.codes is AccessLevel.WRITE
    assert key.unit_access.type is UnitAccessType.BUILDINGS


def test_mod_3_returns_unknown_enum_values_as_strings() -> None:
    steps = [{**CALL["steps"][1], "kind": "teleported", "attempt_result": "maybe"}]  # type: ignore[index]
    call = CallLogEntry.model_validate({**CALL, "result": "voicemail", "steps": steps})
    assert call.result == "voicemail"
    assert type(call.result) is str
    assert call.steps[0].kind == "teleported"
    assert call.steps[0].attempt_result == "maybe"
    assert call.result != CallResult.REJECTED


@pytest.mark.parametrize(
    "enum",
    [
        AccessLevel,
        UnitAccessType,
        DoorDigit,
        CallResult,
        CallStepKind,
        CodeAttemptResult,
        DialStatus,
    ],
)
def test_mod_6_enum_members_format_as_their_value(enum: type[Enum]) -> None:
    for member in enum:
        assert str(member) == member.value
        assert f"{member}" == member.value
        assert f"{member:>20}" == f"{member.value:>20}"


def test_mod_4_request_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        AccessCodeCreate(unit=UNIT, code="4321", colour="red")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        AccessCodeUpdate(colour="red")  # type: ignore[call-arg]


def test_mod_4_request_models_reject_naive_datetimes() -> None:
    naive = datetime(2026, 11, 1)
    with pytest.raises(ValidationError):
        AccessCodeCreate(unit=UNIT, code="4321", expires_at=naive)
    with pytest.raises(ValidationError):
        AccessCodeUpdate(expires_at=naive)


def test_mod_4_create_requires_unit_and_code() -> None:
    with pytest.raises(ValidationError):
        AccessCodeCreate(unit=UNIT)  # type: ignore[call-arg]


def test_mod_4_update_rejects_null_where_the_schema_does() -> None:
    for field in ("unit", "code"):
        with pytest.raises(ValidationError):
            AccessCodeUpdate(**{field: None})
    cleared = AccessCodeUpdate(name=None, expires_at=None)
    assert cleared.model_dump(exclude_unset=True) == {"name": None, "expires_at": None}
    assert AccessCodeUpdate().model_dump(exclude_unset=True) == {}


@pytest.mark.parametrize(
    "bad",
    [
        {"code": "12"},
        {"code": "1234567890123456"},
        {"code": "12a4"},
        {"code": " 1234"},
        {"code": "1234\n"},
        {"code": "١٢٣"},  # Arabic-Indic digits
        {"code": "²²²"},  # superscripts
        {"name": "x" * 256},
    ],
)
def test_mod_5_request_models_enforce_the_schemas_value_rules(bad: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        AccessCodeCreate(**{"unit": UNIT, "code": "4321"} | bad)
    with pytest.raises(ValidationError):
        AccessCodeUpdate(**bad)


def test_mod_5_request_models_accept_values_within_the_rules() -> None:
    for code in ("000", "123456789012345"):
        assert AccessCodeCreate(unit=UNIT, code=code, name="x" * 255).code == code
        assert AccessCodeUpdate(code=code).code == code


def test_mod_5_response_models_keep_values_the_rules_reject() -> None:
    old = AccessCode.model_validate(SAMPLES[4][2] | {"code": "12", "name": "x" * 300})
    assert (old.code, len(old.name or "")) == ("12", 300)


REQUESTS = [(AccessCodeCreate, "AccessCodeRequest"), (AccessCodeUpdate, "PatchedAccessCodeRequest")]
RULES = ("pattern", "minLength", "maxLength")


def _rules(prop: dict[str, Any]) -> dict[str, Any]:
    """A property's value rules, from it or from its non-null `anyOf` branch."""
    return {k: v for branch in prop.get("anyOf", [prop]) for k, v in branch.items() if k in RULES}


@pytest.mark.parametrize(("model", "component"), REQUESTS)
def test_mod_5_request_models_have_the_schemas_value_rules(
    model: type[BaseModel], component: str
) -> None:
    spec = schema_component(component)
    ours = model.model_json_schema()
    assert ours["properties"].keys() == spec["properties"].keys()
    assert set(ours.get("required", [])) == set(spec.get("required", []))
    minimal = {"unit": UNIT, "code": "4321"} if "unit" in ours.get("required", []) else {}
    for name, prop in spec["properties"].items():
        assert _rules(ours["properties"][name]) == _rules(prop), name
        try:
            model(**minimal | {name: None})
            nullable = True
        except ValidationError:
            nullable = False
        assert nullable == prop.get("nullable", False), name


def test_mod_5_request_models_check_types() -> None:
    with pytest.raises(ValidationError):
        AccessCodeCreate(unit=UNIT, code=4321)
    with pytest.raises(ValidationError):
        AccessCodeCreate(unit="not a uuid", code="4321")
