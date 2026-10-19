from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, TextIO

from . import PROTOCOL_VERSION


class ProtocolError(ValueError):
    """Raised when an untrusted worker request is invalid."""


@dataclass(frozen=True)
class Request:
    request_id: str
    operation: str


def parse_request(line: str) -> Request:
    if len(line.encode("utf-8")) > 16_384:
        raise ProtocolError("request exceeds 16384-byte limit")
    try:
        value = json.loads(line)
    except json.JSONDecodeError as error:
        raise ProtocolError("request is not valid JSON") from error
    if not isinstance(value, dict):
        raise ProtocolError("request must be a JSON object")
    if set(value) != {"version", "requestId", "operation"}:
        raise ProtocolError("request fields must be version, requestId, and operation")
    if value["version"] != PROTOCOL_VERSION:
        raise ProtocolError(f"unsupported protocol version: {value['version']!r}")
    request_id = value["requestId"]
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        raise ProtocolError("requestId must be a non-empty string of at most 128 characters")
    operation = value["operation"]
    if operation != "health":
        raise ProtocolError(f"unsupported operation: {operation!r}")
    return Request(request_id=request_id, operation=operation)


def response(request_id: str | None, *, ok: bool, payload: dict[str, Any]) -> str:
    return json.dumps(
        {
            "version": PROTOCOL_VERSION,
            "requestId": request_id,
            "ok": ok,
            **payload,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def serve(
    source: TextIO,
    destination: TextIO,
    *,
    device_info: dict[str, Any],
) -> None:
    for line in source:
        request_id: str | None = None
        try:
            request = parse_request(line)
            request_id = request.request_id
            message = response(
                request_id,
                ok=True,
                payload={"status": "ready", "device": device_info},
            )
        except ProtocolError as error:
            message = response(
                request_id,
                ok=False,
                payload={"error": {"code": "invalid_request", "message": str(error)}},
            )
        destination.write(message + "\n")
        destination.flush()

