"""Backup and restore a BACnet device's configuration.

Demonstrates the full backup/restore workflow using the high-level
Client API. The backup procedure downloads all configuration files
from the device, and the restore procedure uploads them back.

Usage::

    python examples/backup_restore.py
"""

import asyncio

from bac_py import Client


async def main() -> None:
    """Backup a device and restore from that backup."""
    async with Client(instance_number=999) as client:
        addr = "192.168.1.100"

        # Backup: downloads all configuration files
        print("Starting backup...")
        backup_data = await client.backup(addr, password="admin", timeout=60.0)
        print(f"Backup complete for device {backup_data.device_instance}")
        print(f"Downloaded {len(backup_data.configuration_files)} config file(s)")
        for file_oid, data in backup_data.configuration_files:
            print(f"  {file_oid}: {len(data)} bytes")

        # Restore: uploads configuration files back to the device
        print("\nStarting restore...")
        await client.restore(addr, backup_data, password="admin", timeout=60.0)
        print("Restore complete.")


if __name__ == "__main__":
    asyncio.run(main())
