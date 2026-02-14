"""JSON serializer backed by orjson."""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import Any

import orjson

logger = logging.getLogger(__name__)


class JsonSerializer:
    """JSON serializer using orjson for high-performance encoding.

    ``bytes`` and ``memoryview`` values are encoded as hex strings.
    Since JSON has no binary type, deserialization returns them as
    plain strings — callers must use ``bytes.fromhex()`` when
    round-tripping binary data.

    :param pretty: Indent output with 2 spaces.
    :param sort_keys: Sort dict keys alphabetically.
    """

    def __init__(
        self,
        *,
        pretty: bool = False,
        sort_keys: bool = False,
    ) -> None:
        self._options = orjson.OPT_NON_STR_KEYS
        if pretty:
            self._options |= orjson.OPT_INDENT_2
        if sort_keys:
            self._options |= orjson.OPT_SORT_KEYS

    def encode(self, data: dict[str, Any]) -> bytes:
        """Encode a dict to JSON bytes."""
        return orjson.dumps(data, default=self._default, option=self._options)

    def decode(self, raw: bytes) -> dict[str, Any]:
        """Decode JSON bytes to a dict."""
        result = orjson.loads(raw)
        if not isinstance(result, dict):
            msg = f"Expected JSON object, got {type(result).__name__}"
            logger.warning(f"deserialize failed: {msg}")
            raise TypeError(msg)
        return result

    @property
    def content_type(self) -> str:
        """MIME content type for JSON."""
        return "application/json"

    def _default(self, obj: Any) -> Any:
        """Handle BACnet types that orjson cannot serialize natively."""
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if isinstance(obj, bytes):
            return obj.hex()
        if isinstance(obj, memoryview):
            return bytes(obj).hex()
        if isinstance(obj, IntEnum):
            return int(obj)
        msg = f"Cannot serialize {type(obj).__name__}"
        logger.warning(f"serialize failed: {msg}")
        raise TypeError(msg)
