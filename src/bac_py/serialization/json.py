"""JSON serializer backed by orjson."""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import Any

try:
    import orjson
except ImportError:  # pragma: no cover
    orjson = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def json_default(obj: object) -> object:
    """Default handler for serializing BACnet types to JSON.

    Use as the *default* argument to :func:`json.dumps` or
    :func:`orjson.dumps` so that BACnet objects serialize automatically.

    Handles:

    * Objects with a ``to_dict()`` method (``BitString``, ``ObjectIdentifier``,
      ``BACnetDate``, ``BACnetTime``, ``StatusFlags``, and all other BACnet
      constructed types).
    * ``bytes`` and ``memoryview`` → hex string.
    * ``IntEnum`` subclasses (``ObjectType``, ``PropertyIdentifier``, …) → ``int``.

    Example::

        import json
        from bac_py import json_default

        result = await client.read_multiple(...)
        print(json.dumps(result, default=json_default))

    :param obj: The object to convert.
    :returns: A JSON-serializable representation.
    :raises TypeError: If *obj* is not a recognised type.
    """
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, bytes):
        return obj.hex()
    if isinstance(obj, memoryview):
        return bytes(obj).hex()
    if isinstance(obj, IntEnum):
        return int(obj)
    msg = f"Cannot serialize {type(obj).__name__}"
    logger.warning("serialize failed: %s", msg)
    raise TypeError(msg)


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
        if orjson is None:  # pragma: no cover
            msg = "orjson is required for JsonSerializer — install bac-py[serialization]"
            raise ImportError(msg)
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
            logger.warning("deserialize failed: %s", msg)
            raise TypeError(msg)
        return result

    @property
    def content_type(self) -> str:
        """MIME content type for JSON."""
        return "application/json"

    def _default(self, obj: Any) -> Any:
        """Handle BACnet types that orjson cannot serialize natively."""
        return json_default(obj)
