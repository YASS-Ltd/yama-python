"""Check JSON strictly against the vendored OpenAPI schema.

Strict means a field the schema doesn't define is an error, so the fake API
can't drift from the real one by adding or misspelling fields.
"""

import re
from functools import cache
from pathlib import Path
from typing import Any

import httpx
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
def _schema() -> dict[str, Any]:
    with SCHEMA_PATH.open() as f:
        schema: dict[str, Any] = yaml.safe_load(f)
    return schema


@cache
def _components() -> dict[str, Any]:
    components: dict[str, Any] = _forbid_extra(_schema()["components"])
    return components


def validate(component: str, instance: object) -> None:
    """Raise if `instance` doesn't match `#/components/schemas/<component>` exactly."""
    components = _components()
    OAS30Validator({**components["schemas"][component], "components": components}).validate(
        instance
    )


def validate_response(response: httpx.Response) -> None:
    """Raise unless the schema documents `response`'s status for its operation, and its body
    matches that status's schema exactly."""
    request = response.request
    paths = _schema()["paths"]
    template = next(
        (t for t in paths if re.fullmatch(re.sub(r"\{\w+\}", "[^/]+", t), request.url.path)),
        None,
    )
    assert template, f"no operation for {request.url.path}"
    responses = paths[template][request.method.lower()]["responses"]
    status = str(response.status_code)
    assert status in responses, f"{request.method} {template} doesn't document {status}"
    content = responses[status].get("content")
    if content is None:
        assert response.content == b""
        return
    ref = content["application/json"]["schema"]["$ref"]
    validate(ref.rsplit("/", 1)[-1], response.json())
