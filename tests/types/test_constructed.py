"""Tests for BACnet constructed data types."""

from bac_py.types.constructed import StatusFlags
from bac_py.types.primitives import BitString


class TestStatusFlags:
    def test_default_all_false(self):
        sf = StatusFlags()
        assert sf.in_alarm is False
        assert sf.fault is False
        assert sf.overridden is False
        assert sf.out_of_service is False

    def test_constructor_kwargs(self):
        sf = StatusFlags(in_alarm=True, fault=True, overridden=True, out_of_service=True)
        assert sf.in_alarm is True
        assert sf.fault is True
        assert sf.overridden is True
        assert sf.out_of_service is True

    def test_partial_flags(self):
        sf = StatusFlags(fault=True, out_of_service=True)
        assert sf.in_alarm is False
        assert sf.fault is True
        assert sf.overridden is False
        assert sf.out_of_service is True

    def test_to_bit_string(self):
        sf = StatusFlags(in_alarm=True)
        bs = sf.to_bit_string()
        assert isinstance(bs, BitString)
        assert len(bs) == 4
        assert bs[0] is True  # IN_ALARM
        assert bs[1] is False  # FAULT
        assert bs[2] is False  # OVERRIDDEN
        assert bs[3] is False  # OUT_OF_SERVICE

    def test_to_bit_string_all_set(self):
        sf = StatusFlags(in_alarm=True, fault=True, overridden=True, out_of_service=True)
        bs = sf.to_bit_string()
        assert all(bs[i] for i in range(4))

    def test_from_bit_string_roundtrip(self):
        original = StatusFlags(fault=True, out_of_service=True)
        bs = original.to_bit_string()
        restored = StatusFlags.from_bit_string(bs)
        assert restored == original

    def test_to_dict(self):
        sf = StatusFlags(in_alarm=True)
        d = sf.to_dict()
        assert d == {
            "in_alarm": True,
            "fault": False,
            "overridden": False,
            "out_of_service": False,
        }

    def test_from_dict_roundtrip(self):
        original = StatusFlags(overridden=True, out_of_service=True)
        d = original.to_dict()
        restored = StatusFlags.from_dict(d)
        assert restored == original

    def test_equality(self):
        a = StatusFlags(fault=True)
        b = StatusFlags(fault=True)
        c = StatusFlags(in_alarm=True)
        assert a == b
        assert a != c

    def test_equality_not_implemented_for_other_types(self):
        sf = StatusFlags()
        assert sf != "not a status flags"

    def test_repr_normal(self):
        sf = StatusFlags()
        assert repr(sf) == "StatusFlags(NORMAL)"

    def test_repr_with_flags(self):
        sf = StatusFlags(in_alarm=True, fault=True)
        r = repr(sf)
        assert "IN_ALARM" in r
        assert "FAULT" in r
