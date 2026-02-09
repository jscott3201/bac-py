"""External format serialization (JSON, etc.) for BACnet data.

This module provides a pluggable serialization API for converting BACnet
data structures to and from external interchange formats.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["Serializer", "deserialize", "get_serializer", "serialize"]


@runtime_checkable
class Serializer(Protocol):
    """Interface for format-specific serialization backends."""

    def encode(self, data: dict[str, Any]) -> bytes:
        """Encode a dict to the target format."""
        ...

    def decode(self, raw: bytes) -> dict[str, Any]:
        """Decode bytes in the target format to a dict."""
        ...

    @property
    def content_type(self) -> str:
        """MIME type for the output format (e.g. 'application/json')."""
        ...


def get_serializer(format: str = "json", **kwargs: Any) -> Serializer:
    """Get a serializer instance for the given format.

    Args:
        format: Output format. Currently supported: ``"json"``.
        **kwargs: Format-specific options passed to the serializer constructor.

    Returns:
        A Serializer instance.

    Raises:
        ValueError: If the format is not supported.
        ImportError: If the required dependency is not installed.
    """
    if format == "json":
        from bac_py.serialization.json import JsonSerializer

        return JsonSerializer(**kwargs)
    msg = f"Unsupported serialization format: {format}"
    raise ValueError(msg)


def serialize(obj: Any, format: str = "json", **kwargs: Any) -> bytes:
    """Serialize a BACnet object or dict to the specified format.

    Accepts any object with a ``to_dict()`` method, or a plain dict.

    Args:
        obj: Object to serialize.
        format: Output format (default ``"json"``).
        **kwargs: Format-specific options.

    Returns:
        Serialized bytes.
    """
    serializer = get_serializer(format, **kwargs)
    data = obj.to_dict() if hasattr(obj, "to_dict") else obj
    return serializer.encode(data)


def deserialize(raw: bytes, format: str = "json") -> dict[str, Any]:
    """Deserialize bytes to a dict.

    Args:
        raw: Bytes to deserialize.
        format: Input format (default ``"json"``).

    Returns:
        Deserialized dict.
    """
    serializer = get_serializer(format)
    return serializer.decode(raw)
