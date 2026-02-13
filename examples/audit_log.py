"""Query BACnet audit logs.

Demonstrates querying audit records from a device's audit log object
using target-based queries with pagination support.

Usage::

    python examples/audit_log.py
"""

import asyncio

from bac_py import Client
from bac_py.types.audit_types import AuditQueryByTarget
from bac_py.types.primitives import ObjectIdentifier

DEVICE_ADDRESS = "192.168.1.100"


async def main() -> None:
    """Query audit log records by target device."""
    async with Client(instance_number=999) as client:
        # Build a query targeting a specific device's records
        query = AuditQueryByTarget(
            target_device_identifier=ObjectIdentifier(8, 1000),  # device,1000
        )

        # Query the audit log object (audit-log,1)
        result = await client.query_audit_log(
            DEVICE_ADDRESS,
            audit_log="audit-log,1",
            query_parameters=query,
            requested_count=50,
        )

        print(f"Audit log: {result.audit_log}")
        print(f"Records returned: {len(result.records)}")
        for record in result.records:
            print(f"  {record}")

        # Paginate through remaining records
        while not result.no_more_items and result.records:
            last_seq = result.records[-1].sequence_number
            result = await client.query_audit_log(
                DEVICE_ADDRESS,
                audit_log="audit-log,1",
                query_parameters=query,
                start_at_sequence_number=last_seq + 1,
                requested_count=50,
            )
            print(f"  ... {len(result.records)} more record(s)")

        print("\nAll audit records retrieved.")


if __name__ == "__main__":
    asyncio.run(main())
