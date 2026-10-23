"""Test fixtures and path setup for the Lissy integration."""

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(__file__))
# Repo root so `import custom_components.lissy` works (HA integration discovery).
sys.path.insert(0, _ROOT)

# The pytest-homeassistant-custom-component plugin imports its own bundled
# `custom_components` (testing_config) at startup, shadowing ours. Make the repo
# copy discoverable by adding it to the package search path.
import custom_components  # noqa: E402

_OUR_CC = os.path.join(_ROOT, "custom_components")
if _OUR_CC not in custom_components.__path__:
    custom_components.__path__.append(_OUR_CC)

from unittest.mock import AsyncMock, patch  # noqa: E402

from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.lissy.const import DOMAIN  # noqa: E402


async def setup_lissy_entry(
    hass, *, username="12345", options=None, loans=(), card_number=None
):
    """Set up a Lissy entry with a mocked client. Returns (entry, client)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=username,
        title=f"Lissy ({username})",
        data={"username": username, "password": "secret", "base_url": "http://x"},
        options=options or {},
    )
    entry.add_to_hass(hass)

    client = AsyncMock()
    client.list_loans = AsyncMock(
        return_value={"loans": list(loans), "restrictions": []}
    )
    client.renew = AsyncMock(return_value={"renewed": [], "list": list(loans)})
    # Real attribute, not an auto-created mock: the barcode resolution
    # relies on None meaning "portal didn't show the number".
    client.card_number = card_number

    with patch("custom_components.lissy.LissyClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry, client


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable the lissy custom integration for every test."""
    yield
