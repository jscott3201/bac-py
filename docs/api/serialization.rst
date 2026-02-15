Serialization
=============

JSON serialization for BACnet values using ``orjson`` when available. Install
with ``pip install bac-py[serialization]``. Use ``serialize()`` and
``deserialize()`` for round-trip conversion, or ``to_dict()`` / ``from_dict()``
on individual constructed types.

.. automodule:: bac_py.serialization
   :members:

JSON Serializer
---------------

.. automodule:: bac_py.serialization.json
   :members:
