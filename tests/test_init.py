"""Integration setup and renew service tests (H1/H2/H3)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lissy.api import LissyConnectionError
from custom_components.lissy.const import DOMAIN

LOANS = [
    {
        "mednr": "111",
        "medientyp": "Buch",
        "kurztitel": "Book One",
        "leihfrist": "30.06.2026",
        "hinweis": "",
    },
    {
        "mednr": "222",
        "medientyp": "DVD",
        "kurztitel": "DVD Two",
        "leihfrist": "15.07.2026",
        "hinweis": "",
    },
]


async def _setup(hass, list_loans=None, renew=None):
    """Set up a Lissy entry with a mocked client. Returns (entry, client)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="12345",
        title="Lissy (12345)",
        data={"username": "12345", "password": "secret", "base_url": "http://x"},
    )
    entry.add_to_hass(hass)

    client = AsyncMock()
    client.list_loans = list_loans or AsyncMock(return_value=list(LOANS))
    client.renew = renew or AsyncMock(return_value={"renewed": [], "list": list(LOANS)})

    with patch("custom_components.lissy.LissyClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry, client


async def test_setup_creates_entities(hass):
    await _setup(hass)

    # summary sensors + one item sensor per loan + a calendar
    assert hass.states.get("sensor.lissy_12345_borrowed").state == "2"
    assert hass.states.get("sensor.lissy_12345_next_due").state == "2026-06-30"
    assert hass.states.get("sensor.lissy_12345_book_one") is not None
    assert hass.states.get("sensor.lissy_12345_dvd_two") is not None
    assert hass.states.get("calendar.lissy_12345") is not None


async def test_renew_all_via_device(hass):
    """Targeting the Lissy device renews all loans (targets=None)."""
    from homeassistant.helpers import device_registry as dev_reg_helper

    entry, client = await _setup(hass)
    dev_reg = dev_reg_helper.async_get(hass)
    device = dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})

    await hass.services.async_call(
        DOMAIN,
        "renew",
        {},
        target={"device_id": device.id},
        blocking=True,
    )
    client.renew.assert_awaited_once_with(None)


async def test_renew_multiple_items_same_account(hass):
    """H1: targeting two item sensors renews BOTH mednrs in one call."""
    _, client = await _setup(hass)
    reg = er.async_get(hass)
    e1 = reg.async_get("sensor.lissy_12345_book_one")
    e2 = reg.async_get("sensor.lissy_12345_dvd_two")

    await hass.services.async_call(
        DOMAIN,
        "renew",
        {"entity_id": [e1.entity_id, e2.entity_id]},
        blocking=True,
    )

    client.renew.assert_awaited_once()
    (targets,) = client.renew.await_args.args
    assert targets == {"111", "222"}


async def test_renew_does_not_trigger_second_fetch(hass):
    """H2: renew reuses the returned list; no extra list_loans call."""
    renew = AsyncMock(return_value={"renewed": [{"mednr": "111", "verlaengert": True, "grund": ""}], "list": [LOANS[1]]})
    _, client = await _setup(hass, renew=renew)
    calls_before = client.list_loans.await_count

    await hass.services.async_call(
        DOMAIN,
        "renew",
        {"entity_id": "sensor.lissy_12345_book_one"},
        blocking=True,
    )
    await hass.async_block_till_done()

    # no additional list_loans (would be a second full login + scrape)
    assert client.list_loans.await_count == calls_before
    # coordinator state reflects the list renew() returned (one loan left)
    assert hass.states.get("sensor.lissy_12345_borrowed").state == "1"


async def test_renew_summary_sensor_raises(hass):
    """Targeting a non-item sensor (e.g. borrowed count) is a validation error."""
    _, client = await _setup(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "renew",
            {"entity_id": "sensor.lissy_12345_borrowed"},
            blocking=True,
        )
    client.renew.assert_not_awaited()


async def test_renew_connection_error_surfaces(hass):
    """H3: client errors become HomeAssistantError, not raw tracebacks."""
    renew = AsyncMock(side_effect=LissyConnectionError("boom"))
    _, _ = await _setup(hass, renew=renew)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "renew",
            {"entity_id": "sensor.lissy_12345_book_one"},
            blocking=True,
        )


async def test_renew_unknown_mednr_is_validation_error(hass):
    """H3: ValueError from the client → ServiceValidationError."""
    renew = AsyncMock(side_effect=ValueError("Med.nr. 111 not found"))
    _, _ = await _setup(hass, renew=renew)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "renew",
            {"entity_id": "sensor.lissy_12345_book_one"},
            blocking=True,
        )


async def test_renew_failure_surfaces_as_error(hass):
    """A Nein response from the library raises HomeAssistantError with the reason."""
    renew = AsyncMock(return_value={
        "renewed": [{"mednr": "111", "verlaengert": False, "grund": "Keine Fristverlängerung! Nicht innerhalb der nächsten 10 Tage fällig!"}],
        "list": list(LOANS),
    })
    _, _ = await _setup(hass, renew=renew)

    with pytest.raises(HomeAssistantError, match="Keine Fristverlängerung"):
        await hass.services.async_call(
            DOMAIN,
            "renew",
            {"entity_id": "sensor.lissy_12345_book_one"},
            blocking=True,
        )


async def test_returned_book_entity_is_removed(hass):
    """Returning a book removes its entity from the registry entirely."""
    from custom_components.lissy.const import DOMAIN as _DOMAIN

    entry, _ = await _setup(hass)
    reg = er.async_get(hass)

    assert reg.async_get("sensor.lissy_12345_book_one") is not None
    assert reg.async_get("sensor.lissy_12345_dvd_two") is not None

    # Push updated data (book_one returned) directly into the coordinator
    coordinator = hass.data[_DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data([LOANS[1]])
    await hass.async_block_till_done()

    assert reg.async_get("sensor.lissy_12345_book_one") is None
    assert reg.async_get("sensor.lissy_12345_dvd_two") is not None
