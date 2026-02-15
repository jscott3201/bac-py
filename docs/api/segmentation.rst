Segmentation
============

Automatic segmented message assembly and transmission per Clause 5.2.
Messages exceeding the maximum APDU size are transparently split into segments
and reassembled. This works in both directions -- sending segmented requests
and receiving segmented responses.

.. automodule:: bac_py.segmentation
   :no-members:

Segmentation Manager
--------------------

.. automodule:: bac_py.segmentation.manager
   :members:
