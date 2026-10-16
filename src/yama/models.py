"""The models the client takes and returns, and the enums their fields use.

Response models mirror the API's schema field for field. They're frozen, keep fields the
client doesn't know (read them as attributes, or from `model_extra`), and give an enum value
the client doesn't know as a plain string, so compare with `==`. Enum members format as their
value, so `str()` and f-strings give the same text either way. Request models reject unknown
fields and datetimes without a time zone, and leave value rules, such as lengths, to the API.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "AccessCode",
    "AccessCodeCreate",
    "AccessCodeUpdate",
    "AccessLevel",
    "ApiKeyDetails",
    "ApiKeyPermissions",
    "ApiKeyUnitAccess",
    "Building",
    "CallLogEntry",
    "CallLogStep",
    "CallResult",
    "CallStepKind",
    "CodeAttemptResult",
    "Contact",
    "DialStatus",
    "DoorDigit",
    "Unit",
    "UnitAccessType",
]


class _StrEnum(str, Enum):
    """A `str` enum whose members format as their value, in `str()` and f-strings alike."""

    def __str__(self) -> str:
        return str(self.value)


class AccessLevel(_StrEnum):
    """What an API key may do with a resource."""

    NONE = "none"
    READ = "read"
    WRITE = "write"


class UnitAccessType(_StrEnum):
    """Which units an API key reaches: all of them, those in some buildings, or some units."""

    ALL = "all"
    BUILDINGS = "buildings"
    UNITS = "units"


class DoorDigit(_StrEnum):
    """The digit Yama sends to a building's intercom to open the door for a unit."""

    ZERO = "0"
    ONE = "1"
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    SIX = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"


class CallResult(_StrEnum):
    """How a call ended."""

    CODE_ACCEPTED = "code_accepted"
    FORWARDED = "forwarded"
    REJECTED = "rejected"
    ERROR = "error"
    CODE_NOT_ACCEPTED = "code_not_accepted"
    HUNG_UP = "hung_up"
    IN_PROGRESS = "in_progress"
    NOT_RECORDED = "not_recorded"


class CallStepKind(_StrEnum):
    """What happened at one step of a call."""

    RECEIVED = "received"
    REJECTED = "rejected"
    PROMPTED = "prompted"
    INPUT = "input"
    TONE_SENT = "tone_sent"
    DIAL_STARTED = "dial_started"
    DIAL_ENDED = "dial_ended"
    TIME_LIMIT = "time_limit"
    ERROR = "error"
    COMPLETED = "completed"


class CodeAttemptResult(_StrEnum):
    """How a code entered at the intercom was judged."""

    ACCEPTED = "accepted"
    NOT_ACCEPTED = "not_accepted"
    EXPIRED = "expired"
    RETIRED = "retired"
    REFUSED = "refused"


class DialStatus(_StrEnum):
    """How a forwarded call ended."""

    COMPLETED = "completed"
    ANSWERED = "answered"
    NO_ANSWER = "no-answer"
    BUSY = "busy"
    FAILED = "failed"
    CANCELED = "canceled"


# An enum field takes values the client doesn't know too, as plain strings (MOD-3).
_OPEN = Field(union_mode="left_to_right")


class _Response(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiKeyPermissions(_Response):
    """An API key's access level for each resource."""

    codes: Annotated[AccessLevel | str, _OPEN]
    contacts: Annotated[AccessLevel | str, _OPEN]
    call_log: Annotated[AccessLevel | str, _OPEN]
    buildings: Annotated[AccessLevel | str, _OPEN]


class ApiKeyUnitAccess(_Response):
    """The units an API key reaches: `buildings` and `units` list the selected ones."""

    type: Annotated[UnitAccessType | str, _OPEN]
    buildings: list[UUID]
    units: list[UUID]


class ApiKeyDetails(_Response):
    """The API key that sent the request: what it may do, never the key itself."""

    uuid: UUID
    name: str
    created_at: AwareDatetime
    expires_at: AwareDatetime | None
    """None for a key that never expires."""
    last_used_at: AwareDatetime | None
    permissions: ApiKeyPermissions
    scopes: list[str]
    unit_access: ApiKeyUnitAccess


class Building(_Response):
    """A building, with the number its intercom calls from and how many of your units it has."""

    uuid: UUID
    name: str
    address: str
    caller_id: str
    unit_count: int


class Unit(_Response):
    """A unit in a building."""

    uuid: UUID
    building: UUID | None
    name: str
    door_digit: Annotated[DoorDigit | str, _OPEN]
    dial_in_number: str | None


class Contact(_Response):
    """Someone a visitor can be forwarded to from a unit's intercom menu."""

    uuid: UUID
    unit: UUID
    number: str
    menu_digit: str
    name: str


class AccessCode(_Response):
    """An access code on a unit."""

    uuid: UUID
    unit: UUID
    code: str
    name: str | None = None
    expires_at: AwareDatetime | None = None
    """When the code stops working; None for a code that never expires."""


class CallLogStep(_Response):
    """One step of a call. Facts that don't apply to the step are None."""

    kind: Annotated[CallStepKind | str, _OPEN]
    at: AwareDatetime
    text: str
    attempt_result: Annotated[CodeAttemptResult | str | None, _OPEN]
    entered_digits: str | None
    code_name: str | None
    contact_name: str | None
    dial_status: Annotated[DialStatus | str | None, _OPEN]


class CallLogEntry(_Response):
    """A call to a unit through a building's intercom, with its steps."""

    uuid: UUID
    unit: UUID
    building: UUID | None
    reference: str
    started_at: AwareDatetime
    duration_seconds: int | None
    result: Annotated[CallResult | str, _OPEN]
    result_label: str
    summary: str
    imported: bool
    steps: list[CallLogStep]


class AccessCodeCreate(_Request):
    """A new access code, or the whole of one being replaced.

    `name` is optional. Leave `expires_at` out for a code that never expires; when replacing,
    leaving it out keeps the current expiry and None clears it. The API doesn't say what
    leaving `name` out does on a replace, so pass the name the code should have.
    """

    unit: UUID
    code: str
    name: str | None = None
    expires_at: AwareDatetime | None = None


class AccessCodeUpdate(_Request):
    """Changes to an access code: only the fields you set are sent. Setting `name` or
    `expires_at` to None clears it; `code` and `unit` can't be cleared."""

    unit: UUID | None = None
    code: str | None = None
    name: str | None = None
    expires_at: AwareDatetime | None = None

    @field_validator("unit", "code")
    @classmethod
    def _not_null(cls, value: object) -> object:
        """The API doesn't take null for these (MOD-4); leaving them out is fine."""
        if value is None:
            raise ValueError("can't be None; leave it out to keep the current value")
        return value
