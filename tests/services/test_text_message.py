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


# ---------------------------------------------------------------------------
# Coverage: text_message.py branch partial 98->102
# ---------------------------------------------------------------------------


class TestConfirmedTextMessageRequestMessageClassChoice:
    """Branch 98->102: messageClass CHOICE fallthrough in TextMessage.decode.

    When the inner messageClass tag number is neither 0 nor 1, both
    conditionals fail and the code falls through with neither field set.
    """

    def test_message_class_unknown_choice(self):
        """MessageClass with unknown CHOICE tag number (not 0 or 1).

        Manually construct data with messageClass containing tag number 5.
        """
        from bac_py.encoding.primitives import (
            encode_character_string,
            encode_context_object_id,
            encode_context_tagged,
            encode_enumerated,
            encode_unsigned,
        )
        from bac_py.encoding.tags import encode_closing_tag, encode_opening_tag
        from bac_py.types.enums import ObjectType
        from bac_py.types.primitives import ObjectIdentifier

        buf = bytearray()
        # [0] textMessageSourceDevice
        buf.extend(encode_context_object_id(0, ObjectIdentifier(ObjectType.DEVICE, 1)))
        # [1] messageClass (constructed) with unknown inner tag number 5
        buf.extend(encode_opening_tag(1))
        buf.extend(encode_context_tagged(5, encode_unsigned(42)))
        buf.extend(encode_closing_tag(1))
        # [2] messagePriority = NORMAL (0)
        buf.extend(encode_context_tagged(2, encode_enumerated(0)))
        # [3] message
        buf.extend(encode_context_tagged(3, encode_character_string("Hello")))

        decoded = ConfirmedTextMessageRequest.decode(bytes(buf))
        assert decoded.message_class_numeric is None
        assert decoded.message_class_character is None
        assert decoded.message == "Hello"
        assert decoded.message_priority == MessagePriority.NORMAL
