"""Barcode image entity tests (opt-in via the options flow flag)."""

from __future__ import annotations

import io

import barcode
from homeassistant.components.image import async_get_image
from homeassistant.helpers import entity_registry as er
from PIL import Image

from conftest import setup_lissy_entry
from custom_components.lissy.const import DOMAIN
from custom_components.lissy.image import _generate_code39_png, code39_value


async def test_no_barcode_by_default(hass):
    """Without the option the image entity is not created."""
    await setup_lissy_entry(hass)
    assert hass.states.get("image.lissy_12345_barcode") is None


async def test_opt_in_creates_image_entity(hass):
    """With show_barcode the image entity serves a Code39 PNG."""
    await setup_lissy_entry(hass, options={"show_barcode": True})

    state = hass.states.get("image.lissy_12345_barcode")
    assert state is not None
    assert state.state  # image_last_updated timestamp

    image = await async_get_image(hass, "image.lissy_12345_barcode")
    assert image.content_type == "image/png"
    assert image.content.startswith(b"\x89PNG")

    img = Image.open(io.BytesIO(image.content))
    # ~420x170 px for the default 5-digit ID.
    assert 350 <= img.width <= 600
    assert 160 <= img.height <= 180
    # No portal number in this fixture — username fallback.
    assert image.content == _generate_code39_png("12345")


async def test_scraped_card_number_takes_precedence(hass):
    """The barcode encodes the portal's number (leading zero included)."""
    await setup_lissy_entry(
        hass, username="3505383", card_number="03505383", options={"show_barcode": True}
    )

    state = hass.states.get("sensor.lissy_3505383_borrowed")
    assert state.attributes["card_number"] == "03505383"

    image = await async_get_image(hass, "image.lissy_3505383_barcode")
    assert image.content == _generate_code39_png("03505383")
    assert image.content != _generate_code39_png("3505383")


async def test_lowercase_username_renders_uppercase(hass):
    """Lowercase letters are encoded as uppercase (documented behaviour)."""
    await setup_lissy_entry(hass, username="ab12", options={"show_barcode": True})

    image = await async_get_image(hass, "image.lissy_ab12_barcode")
    assert image.content == _generate_code39_png("AB12")


async def test_setup_skips_entity_for_unencodable_username(hass):
    """An enabled option with an unencodable username creates no entity."""
    entry, _ = await setup_lissy_entry(
        hass, username="12ä34", options={"show_barcode": True}
    )

    registry = er.async_get(hass)
    unique_id = f"{entry.entry_id}_barcode"
    assert registry.async_get_entity_id("image", DOMAIN, unique_id) is None


def test_code39_value_uppercases():
    """Lowercase is uppercased; digits and spaces pass through unchanged."""
    assert code39_value("ab12") == "AB12"
    assert code39_value(" 12 34 ") == " 12 34 "


def test_code39_value_rejects_unencodable():
    """Characters outside the Code39 alphabet yield None."""
    assert code39_value("äöü") is None
    assert code39_value("12#34") is None


async def test_generate_code39_png_distinct_per_value():
    """Different account numbers render different barcodes."""
    png_a = _generate_code39_png("12345")
    png_b = _generate_code39_png("99999")
    assert png_a is not None
    assert png_b is not None
    assert png_a != png_b


def test_generate_code39_png_rejects_unencodable():
    """Characters outside the Code39 alphabet produce None, not a crash."""
    assert _generate_code39_png("äöü") is None


def test_generate_code39_png_no_checksum(monkeypatch):
    """The barcode encodes exactly the account number — no mod-43 checksum."""
    captured: dict = {}
    orig = barcode.get

    def spy(name, code, writer=None, options=None):
        captured["options"] = options
        return orig(name, code, writer=writer, options=options)

    monkeypatch.setattr("custom_components.lissy.image.barcode.get", spy)
    assert _generate_code39_png("12345") is not None
    assert captured["options"] == {"add_checksum": False}
