"""Tests for text message services."""

from bac_py.services.text_message import (
    ConfirmedTextMessageRequest,
    UnconfirmedTextMessageRequest,
)
from bac_py.types.enums import MessagePriority, ObjectType
from bac_py.types.primitives import ObjectIdentifier


class TestConfirmedTextMessageRequest:
    def test_round_trip_minimal(self):
        request = ConfirmedTextMessageRequest(
            text_message_source_device=ObjectIdentifier(ObjectType.DEVICE, 100),
            message_priority=MessagePriority.NORMAL,
            message="Hello BACnet",
        )
        encoded = request.encode()
        decoded = ConfirmedTextMessageRequest.decode(encoded)
        assert decoded.text_message_source_device == ObjectIdentifier(ObjectType.DEVICE, 100)
        assert decoded.message_priority == MessagePriority.NORMAL
        assert decoded.message == "Hello BACnet"
        assert decoded.message_class_numeric is None
        assert decoded.message_class_character is None

    def test_round_trip_numeric_class(self):
        request = ConfirmedTextMessageRequest(
            text_message_source_device=ObjectIdentifier(ObjectType.DEVICE, 42),
            message_priority=MessagePriority.URGENT,
            message="Fire alarm",
            message_class_numeric=5,
        )
        encoded = request.encode()
        decoded = ConfirmedTextMessageRequest.decode(encoded)
        assert decoded.text_message_source_device == ObjectIdentifier(ObjectType.DEVICE, 42)
        assert decoded.message_priority == MessagePriority.URGENT
        assert decoded.message == "Fire alarm"
        assert decoded.message_class_numeric == 5
        assert decoded.message_class_character is None

    def test_round_trip_character_class(self):
        request = ConfirmedTextMessageRequest(
            text_message_source_device=ObjectIdentifier(ObjectType.DEVICE, 1),
            message_priority=MessagePriority.NORMAL,
            message="Status update",
            message_class_character="maintenance",
        )
        encoded = request.encode()
        decoded = ConfirmedTextMessageRequest.decode(encoded)
        assert decoded.message_class_character == "maintenance"
        assert decoded.message_class_numeric is None
        assert decoded.message == "Status update"

    def test_urgent_priority(self):
        request = ConfirmedTextMessageRequest(
            text_message_source_device=ObjectIdentifier(ObjectType.DEVICE, 1),
            message_priority=MessagePriority.URGENT,
            message="Emergency",
        )
        encoded = request.encode()
        decoded = ConfirmedTextMessageRequest.decode(encoded)
        assert decoded.message_priority == MessagePriority.URGENT


class TestUnconfirmedTextMessageRequest:
    def test_round_trip_minimal(self):
        request = UnconfirmedTextMessageRequest(
            text_message_source_device=ObjectIdentifier(ObjectType.DEVICE, 200),
            message_priority=MessagePriority.NORMAL,
            message="Broadcast message",
        )
        encoded = request.encode()
        decoded = UnconfirmedTextMessageRequest.decode(encoded)
        assert decoded.text_message_source_device == ObjectIdentifier(ObjectType.DEVICE, 200)
        assert decoded.message == "Broadcast message"

    def test_round_trip_with_numeric_class(self):
        request = UnconfirmedTextMessageRequest(
            text_message_source_device=ObjectIdentifier(ObjectType.DEVICE, 10),
            message_priority=MessagePriority.URGENT,
            message="Alert!",
            message_class_numeric=99,
        )
        encoded = request.encode()
        decoded = UnconfirmedTextMessageRequest.decode(encoded)
        assert decoded.message_class_numeric == 99
        assert decoded.message_priority == MessagePriority.URGENT

    def test_inherits_from_confirmed(self):
        assert issubclass(UnconfirmedTextMessageRequest, ConfirmedTextMessageRequest)
