"""Scenario 7: COV subscription operations over real UDP."""

from __future__ import annotations

import asyncio
import contextlib
import os

import pytest

from bac_py import Client

SERVER = os.environ.get("SERVER_ADDRESS", "172.30.1.102")
INSTANCE = int(os.environ.get("SERVER_INSTANCE", "601"))

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    async with Client(instance_number=951, port=0) as c:
        yield c


# --- Basic COV subscription ---


async def test_subscribe_cov_confirmed(client: Client):
    """Subscribe to COV with confirmed notifications, then unsubscribe."""
    await client.subscribe_cov_ex(
        SERVER,
        "av,1",
        process_id=1,
        confirmed=True,
        lifetime=300,
    )
    # If we reach here, subscription succeeded (no BACnet error/abort)
    await client.unsubscribe_cov_ex(SERVER, "av,1", process_id=1)


async def test_subscribe_cov_unconfirmed(client: Client):
    """Subscribe to COV with unconfirmed notifications, then unsubscribe."""
    await client.subscribe_cov_ex(
        SERVER,
        "av,1",
        process_id=2,
        confirmed=False,
        lifetime=300,
    )
    await client.unsubscribe_cov_ex(SERVER, "av,1", process_id=2)


# --- COV with notification callback ---


async def test_cov_notification_on_write(client: Client):
    """Subscribe with callback, write to trigger COV, verify notification arrives."""
    notifications: list = []

    def on_cov(notification, source):
        notifications.append(notification)

    await client.subscribe_cov_ex(
        SERVER,
        "av,1",
        process_id=10,
        confirmed=True,
        lifetime=300,
        callback=on_cov,
    )
    try:
        # Write a different value to trigger a COV notification
        await client.write(SERVER, "av,1", "present-value", 55.0)
        await asyncio.sleep(2)
        assert len(notifications) >= 1
    finally:
        # Cleanup: unsubscribe and restore original value
        await client.unsubscribe_cov_ex(SERVER, "av,1", process_id=10)
        await client.write(SERVER, "av,1", "present-value", 70.0)


# --- COV property-level subscription ---


async def test_subscribe_cov_property(client: Client):
    """Subscribe to COV on a specific property of an object."""
    await client.subscribe_cov_property(
        SERVER,
        "av,1",
        "present-value",
        process_id=20,
        confirmed=True,
        lifetime=300,
    )
    # Reaching here means the subscription was accepted
    # Property-level unsubscribe uses the same unsubscribe_cov_ex
    await client.unsubscribe_cov_ex(SERVER, "av,1", process_id=20)


# --- Subscription lifecycle ---


async def test_unsubscribe_cov(client: Client):
    """Subscribe and then immediately unsubscribe with no errors."""
    await client.subscribe_cov_ex(
        SERVER,
        "av,1",
        process_id=30,
        confirmed=True,
        lifetime=300,
    )
    await client.unsubscribe_cov_ex(SERVER, "av,1", process_id=30)


async def test_subscribe_cov_with_short_lifetime(client: Client):
    """Subscribe with a short lifetime, verify notification, then verify expiry."""
    notifications: list = []

    def on_cov(notification, source):
        notifications.append(notification)

    await client.subscribe_cov_ex(
        SERVER,
        "av,1",
        process_id=40,
        confirmed=True,
        lifetime=5,
        callback=on_cov,
    )
    try:
        # Write to trigger a notification while subscription is alive
        await client.write(SERVER, "av,1", "present-value", 60.0)
        await asyncio.sleep(2)
        count_before_expiry = len(notifications)
        assert count_before_expiry >= 1

        # Wait for the subscription to expire (lifetime=5s + margin)
        await asyncio.sleep(5)

        # Write again after expiry -- should not produce a new notification
        await client.write(SERVER, "av,1", "present-value", 65.0)
        await asyncio.sleep(2)
        assert len(notifications) == count_before_expiry
    finally:
        # Best-effort unsubscribe (may already be expired) and restore value
        with contextlib.suppress(Exception):
            await client.unsubscribe_cov_ex(SERVER, "av,1", process_id=40)
        await client.write(SERVER, "av,1", "present-value", 70.0)


# --- Multiple subscriptions ---


async def test_multiple_cov_subscriptions(client: Client):
    """Subscribe to COV on two different objects with distinct process IDs."""
    await client.subscribe_cov_ex(
        SERVER,
        "av,1",
        process_id=50,
        confirmed=True,
        lifetime=300,
    )
    await client.subscribe_cov_ex(
        SERVER,
        "bv,1",
        process_id=51,
        confirmed=True,
        lifetime=300,
    )
    # Both subscriptions succeeded
    await client.unsubscribe_cov_ex(SERVER, "bv,1", process_id=51)
    await client.unsubscribe_cov_ex(SERVER, "av,1", process_id=50)
