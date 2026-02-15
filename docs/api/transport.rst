Transport
=========

Transport implementations for all supported BACnet data links. Each transport
provides ``start()``, ``stop()``, ``send_unicast()``, ``send_broadcast()``,
and ``on_receive()`` methods conforming to the
:class:`~bac_py.transport.port.TransportPort` protocol.

For setup guides and configuration examples, see :doc:`/guide/transport-setup`.
For BACnet/SC specifics (TLS, hub, failover), see :doc:`/guide/secure-connect`.

.. automodule:: bac_py.transport
   :no-members:

BVLL
----

.. automodule:: bac_py.transport.bvll
   :members:

BACnet/IP
---------

.. automodule:: bac_py.transport.bip
   :members:

BBMD
----

.. automodule:: bac_py.transport.bbmd
   :members:

Foreign Device
--------------

.. automodule:: bac_py.transport.foreign_device
   :members:

BACnet/IPv6 BVLL
-----------------

.. automodule:: bac_py.transport.bvll_ipv6
   :members:

BACnet/IPv6 Transport
---------------------

.. automodule:: bac_py.transport.bip6
   :members:

BACnet/IPv6 BBMD
-----------------

.. automodule:: bac_py.transport.bbmd6
   :members:

BACnet/IPv6 Foreign Device
---------------------------

.. automodule:: bac_py.transport.foreign_device6
   :members:

BACnet Ethernet
----------------

.. automodule:: bac_py.transport.ethernet
   :members:

Transport Port
--------------

.. automodule:: bac_py.transport.port
   :members:

BACnet Secure Connect
---------------------

.. automodule:: bac_py.transport.sc
   :members:

SC BVLC Codec
~~~~~~~~~~~~~~

.. automodule:: bac_py.transport.sc.bvlc
   :members:

SC VMAC Addressing
~~~~~~~~~~~~~~~~~~~

.. automodule:: bac_py.transport.sc.vmac
   :members:

SC Connection
~~~~~~~~~~~~~~

.. automodule:: bac_py.transport.sc.connection
   :members:

SC Hub Function
~~~~~~~~~~~~~~~~

.. automodule:: bac_py.transport.sc.hub_function
   :members:

SC Hub Connector
~~~~~~~~~~~~~~~~~

.. automodule:: bac_py.transport.sc.hub_connector
   :members:

SC Node Switch
~~~~~~~~~~~~~~~

.. automodule:: bac_py.transport.sc.node_switch
   :members:

SC WebSocket
~~~~~~~~~~~~~

.. automodule:: bac_py.transport.sc.websocket
   :members:

SC TLS
~~~~~~~

.. automodule:: bac_py.transport.sc.tls
   :members:

SC Types
~~~~~~~~~

.. automodule:: bac_py.transport.sc.types
   :members:
