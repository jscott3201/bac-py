Network
=======

The network layer handles NPDU encoding/decoding, address parsing, and
multi-port routing. It sits between the application layer (APDUs) and the
transport layer (raw datagrams).

For address format details, see :ref:`addressing`. For router configuration,
see :ref:`transport-router`.

.. automodule:: bac_py.network
   :no-members:

Addressing
----------

.. automodule:: bac_py.network.address
   :members:

NPDU
----

.. automodule:: bac_py.network.npdu
   :members:

Network Messages
----------------

.. automodule:: bac_py.network.messages
   :members:

Network Layer
-------------

.. automodule:: bac_py.network.layer
   :members:

Router
------

.. automodule:: bac_py.network.router
   :members:
