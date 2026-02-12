"""Tests for virtual terminal services."""

from bac_py.services.virtual_terminal import (
    VTCloseRequest,
    VTDataACK,
    VTDataRequest,
    VTOpenACK,
    VTOpenRequest,
)
from bac_py.types.enums import VTClass


class TestVTOpenRequest:
    def test_round_trip(self):
        request = VTOpenRequest(
            vt_class=VTClass.DEFAULT_TERMINAL,
            local_vt_session_identifier=1,
        )
        encoded = request.encode()
        decoded = VTOpenRequest.decode(encoded)
        assert decoded.vt_class == VTClass.DEFAULT_TERMINAL
        assert decoded.local_vt_session_identifier == 1

    def test_round_trip_ansi(self):
        request = VTOpenRequest(
            vt_class=VTClass.ANSI_X3_64,
            local_vt_session_identifier=255,
        )
        encoded = request.encode()
        decoded = VTOpenRequest.decode(encoded)
        assert decoded.vt_class == VTClass.ANSI_X3_64
        assert decoded.local_vt_session_identifier == 255


class TestVTOpenACK:
    def test_round_trip(self):
        ack = VTOpenACK(remote_vt_session_identifier=42)
        encoded = ack.encode()
        decoded = VTOpenACK.decode(encoded)
        assert decoded.remote_vt_session_identifier == 42


class TestVTCloseRequest:
    def test_round_trip_single(self):
        request = VTCloseRequest(
            list_of_remote_vt_session_identifiers=[5],
        )
        encoded = request.encode()
        decoded = VTCloseRequest.decode(encoded)
        assert decoded.list_of_remote_vt_session_identifiers == [5]

    def test_round_trip_multiple(self):
        request = VTCloseRequest(
            list_of_remote_vt_session_identifiers=[1, 2, 3],
        )
        encoded = request.encode()
        decoded = VTCloseRequest.decode(encoded)
        assert decoded.list_of_remote_vt_session_identifiers == [1, 2, 3]


class TestVTDataRequest:
    def test_round_trip(self):
        request = VTDataRequest(
            vt_session_identifier=1,
            vt_new_data=b"Hello VT\r\n",
            vt_data_flag=False,
        )
        encoded = request.encode()
        decoded = VTDataRequest.decode(encoded)
        assert decoded.vt_session_identifier == 1
        assert decoded.vt_new_data == b"Hello VT\r\n"
        assert decoded.vt_data_flag is False

    def test_round_trip_with_flag(self):
        request = VTDataRequest(
            vt_session_identifier=42,
            vt_new_data=b"\x1b[2J",
            vt_data_flag=True,
        )
        encoded = request.encode()
        decoded = VTDataRequest.decode(encoded)
        assert decoded.vt_session_identifier == 42
        assert decoded.vt_new_data == b"\x1b[2J"
        assert decoded.vt_data_flag is True

    def test_round_trip_empty_data(self):
        request = VTDataRequest(
            vt_session_identifier=1,
            vt_new_data=b"",
            vt_data_flag=True,
        )
        encoded = request.encode()
        decoded = VTDataRequest.decode(encoded)
        assert decoded.vt_new_data == b""
        assert decoded.vt_data_flag is True


class TestVTDataACK:
    def test_round_trip_all_accepted(self):
        ack = VTDataACK(all_new_data_accepted=True)
        encoded = ack.encode()
        decoded = VTDataACK.decode(encoded)
        assert decoded.all_new_data_accepted is True
        assert decoded.accepted_octet_count is None

    def test_round_trip_partial(self):
        ack = VTDataACK(
            all_new_data_accepted=False,
            accepted_octet_count=50,
        )
        encoded = ack.encode()
        decoded = VTDataACK.decode(encoded)
        assert decoded.all_new_data_accepted is False
        assert decoded.accepted_octet_count == 50
