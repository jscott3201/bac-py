Application
===========

The application layer is the primary interface for building BACnet clients and
servers. It manages the lifecycle of transports, network layer, transaction
state machine, COV subscriptions, and background engines.

- **Client API** -- :class:`~bac_py.client.Client` (convenience) and
  :class:`~bac_py.app.client.BACnetClient` (protocol-level). See
  :doc:`/guide/client-guide` for usage.
- **Server API** -- :class:`~bac_py.app.server.DefaultServerHandlers` and
  custom handler registration. See :doc:`/guide/server-mode` for usage.
- **Engines** -- EventEngine, ScheduleEngine, TrendLogEngine, AuditManager,
  COVManager. See :doc:`/guide/events-alarms` and :doc:`/guide/server-mode`.

.. automodule:: bac_py.app
   :no-members:

.. toctree::
   :maxdepth: 2

   client
   server
   engines
