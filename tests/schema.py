"""Check JSON strictly against the vendored OpenAPI schema.

Strict means a field the schema doesn't define is an error, so the fake API
can't drift from the real one by adding or misspelling fields.
"""

import json
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


def schema_component(name: str) -> dict[str, Any]:
    """`#/components/schemas/<name>`, as the schema states it."""
    component: dict[str, Any] = _schema()["components"]["schemas"][name]
    return component


def operations() -> dict[str, dict[str, Any]]:
    """Every operation in the schema, by its `operationId`."""
    return {
        operation["operationId"]: operation
        for path in _schema()["paths"].values()
        for operation in path.values()
    }


def methods() -> list[tuple[str, str]]:
    """Every (method, path template) the schema offers."""
    return [(m.upper(), path) for path, ops in _schema()["paths"].items() for m in ops]


def _path(request: httpx.Request) -> dict[str, Any]:
    """The schema's operations on `request`'s path, by method."""
    paths = _schema()["paths"]
    template = next(
        (t for t in paths if re.fullmatch(re.sub(r"\{\w+\}", "[^/]+", t), request.url.path)),
        None,
    )
    assert template, f"no operation for {request.url.path}"
    found: dict[str, Any] = paths[template]
    return found


def operation(request: httpx.Request) -> dict[str, Any]:
    """The schema's operation for `request`."""
    found: dict[str, Any] = _path(request)[request.method.lower()]
    return found


def validate_request(request: httpx.Request) -> None:
    """Raise unless the schema documents `request`'s operation, each of its query parameters
    and its `Idempotency-Key` header, and its body matches the operation's schema exactly."""
    op = operation(request)
    documented = {(p["in"], p["name"].lower()) for p in op.get("parameters", [])}
    for name in request.url.params:
        assert ("query", name) in documented, f"{name} isn't a query parameter"
    if "Idempotency-Key" in request.headers:
        assert ("header", "idempotency-key") in documented, "Idempotency-Key isn't documented"
    body = op.get("requestBody")
    if body is None:
        assert request.content == b""
        return
    ref = body["content"]["application/json"]["schema"]["$ref"]
    validate(ref.rsplit("/", 1)[-1], json.loads(request.content))


def validate_response(response: httpx.Response) -> None:
    """Raise unless the schema documents `response`'s status for its operation, and its body
    matches that status's schema exactly."""
    request = response.request
    # The schema's guide gives these for every endpoint, but the operations don't list them.
    if response.status_code == 405:
        assert request.method.lower() not in _path(request), f"{request.method} is offered"
        validate("Error", response.json())
        return
    if response.status_code == 415:
        offered = _path(request).get(request.method.lower(), {})
        assert "requestBody" in offered, f"{request.method} takes no body"
        media_type = request.headers.get("Content-Type", "").split(";")[0].strip().lower()
        assert request.content and media_type != "application/json", "the body is JSON"
        validate("Error", response.json())
        return
    responses = operation(request)["responses"]
    status = str(response.status_code)
    assert status in responses, f"{request.method} {request.url.path} doesn't document {status}"
    content = responses[status].get("content")
    if content is None:
        assert response.content == b""
        return
    ref = content["application/json"]["schema"]["$ref"]
    validate(ref.rsplit("/", 1)[-1], response.json())
