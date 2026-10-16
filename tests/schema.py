"""Check JSON strictly against the vendored OpenAPI schema.

Strict means a field the schema doesn't define is an error, so the fake API
can't drift from the real one by adding or misspelling fields.
"""

from functools import cache
from pathlib import Path
from typing import Any

import yaml
from openapi_schema_validator import OAS30Validator

SCHEMA_PATH = Path(__file__).parent / "fixtures" / "openapi.yaml"


def _forbid_extra(node: Any) -> Any:
    if isinstance(node, dict):
        node = {k: _forbid_extra(v) for k, v in node.items()}
        if "properties" in node and "additionalProperties" not in node:
            node["additionalProperties"] = False
    elif isinstance(node, list):
        node = [_forbid_extra(v) for v in node]
    return node


@cache
def _components() -> dict[str, Any]:
    with SCHEMA_PATH.open() as f:
        schema: dict[str, Any] = yaml.safe_load(f)
    components: dict[str, Any] = _forbid_extra(schema["components"])
    return components


def validate(component: str, instance: object) -> None:
    """Raise if `instance` doesn't match `#/components/schemas/<component>` exactly."""
    components = _components()
    OAS30Validator({**components["schemas"][component], "components": components}).validate(
        instance
    )
