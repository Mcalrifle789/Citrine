"""The Citrine wire protocol.

One envelope shape for every message, so the transport layer can demultiplex
without special cases. Streaming is a request that yields many events sharing
the request's id.

The ``request`` type is deliberately bidirectional: slice 4's tool
confirmation becomes a server-to-client request that the client answers with
a response, requiring no protocol migration. The tool frames are declared
here but not implemented in this slice.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ValidationError

SERVER_VERSION = "0.1.0"


class MessageType(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    ERROR = "error"


class ErrorCode(str, Enum):
    """The fixed provider-error taxonomy from spec §7."""

    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    QUOTA = "quota"
    NETWORK = "network"
    MODEL_NOT_FOUND = "model_not_found"
    CONTEXT_LENGTH = "context_length"
    SERVER = "server"


class Method(str, Enum):
    AUTH = "auth"
    ECHO = "echo"
    COMMAND_RUN = "command.run"
    CHAT_SEND = "chat.send"
    CHAT_CANCEL = "chat.cancel"
    CHAT_DELTA = "chat.delta"
    CHAT_DONE = "chat.done"
    CHAT_ERROR = "chat.error"
    # Declared for slice 4; not implemented in this slice.
    TOOL_CONFIRM = "tool.confirm"


class Envelope(BaseModel):
    id: str = Field(min_length=1)
    type: MessageType
    method: str
    params: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "id": self.id,
                "type": self.type.value,
                "method": self.method,
                "params": self.params,
            },
            separators=(", ", ": "),
        )


# Params payloads. These document the shapes; the envelope carries them as
# plain dicts so unknown future fields survive a round trip.


class AuthParams(BaseModel):
    token: str


class AuthResult(BaseModel):
    ok: bool
    server_version: str = SERVER_VERSION


class EchoParams(BaseModel):
    text: str


class ChatDelta(BaseModel):
    content: str


class ChatDone(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str


class ErrorPayload(BaseModel):
    code: ErrorCode
    message: str
    correlation_id: str


def parse_envelope(raw: str) -> Envelope:
    """Parse a wire frame, raising ValueError on anything malformed."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON frame: {exc}") from exc

    try:
        return Envelope.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"invalid envelope: {exc}") from exc


def make_envelope(
    envelope_id: str,
    message_type: MessageType,
    method: str,
    params: dict[str, Any] | None = None,
) -> Envelope:
    return Envelope(id=envelope_id, type=message_type, method=method, params=params or {})
