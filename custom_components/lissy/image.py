"""Image platform: the library account number as a scannable barcode."""

from __future__ import annotations

import io
import logging
import string

import barcode
from barcode.writer import ImageWriter

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_SHOW_BARCODE, DEFAULT_SHOW_BARCODE, DOMAIN
from .coordinator import LissyConfigEntry
from .entity import LissyDeviceInfo

_LOGGER = logging.getLogger(__name__)

# Millimetre-based writer options, rendered at 300 dpi: a 5-digit account
# number comes out at roughly 420x155 px, with a quiet zone (border) wide
# enough for barcode scanners to lock onto and 0.25 mm narrow bars with
# comfortable scan margin.
_WRITE_OPTIONS: dict[str, float | int] = {
    "module_width": 0.25,
    "module_height": 8.0,
    "font_size": 6,
    "text_distance": 3,
    "quiet_zone": 4.0,
}

# Code39 alphabet (after uppercasing): digits, uppercase letters, space and
# the punctuation Code39 supports.
_CODE39_ALPHABET = set(string.ascii_uppercase + string.digits + " -.$/+%")


def code39_value(username: str) -> str | None:
    """Normalize an account number for Code39.

    Lowercase letters are uppercased (documented behaviour: the barcode is
    case-insensitive). Returns None when the value contains characters
    outside the Code39 alphabet, which cannot be encoded exactly.
    """
    value = username.upper()
    if set(value) - _CODE39_ALPHABET:
        return None
    return value


def _generate_code39_png(username: str) -> bytes | None:
    """Render the account number as a Code39 PNG; None if not encodable."""
    if (value := code39_value(username)) is None:
        _LOGGER.warning(
            "Cannot render barcode: account number contains characters "
            "outside the Code39 alphabet (A-Z, 0-9, space, - . $ / + %)"
        )
        return None
    code = barcode.get(
        "code39", value, writer=ImageWriter(), options={"add_checksum": False}
    )
    buf = io.BytesIO()
    code.write(buf, _WRITE_OPTIONS)
    return buf.getvalue()


def _barcode_unique_id(entry: ConfigEntry) -> str:
    return f"{entry.entry_id}_barcode"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LissyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the barcode image entity when the option is enabled."""
    if not entry.options.get(CONF_SHOW_BARCODE, DEFAULT_SHOW_BARCODE):
        # Option turned off: drop any barcode entity left in the registry so it
        # doesn't linger as a restored/unavailable state (same as item sensors).
        registry = er.async_get(hass)
        if entity_id := registry.async_get_entity_id(
            "image", DOMAIN, _barcode_unique_id(entry)
        ):
            registry.async_remove(entity_id)
        return

    if code39_value(entry.data["username"]) is None:
        _LOGGER.warning(
            "Barcode option is enabled for %s, but the account number "
            "cannot be encoded as Code39 — skipping the barcode entity",
            entry.title,
        )
        return

    async_add_entities([LissyBarcodeImage(hass, entry)])


class LissyBarcodeImage(LissyDeviceInfo, ImageEntity):
    """Renders the library account number as a Code39 barcode image."""

    _attr_has_entity_name = True
    _attr_name = "Barcode"
    _attr_icon = "mdi:barcode"
    _attr_content_type = "image/png"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        # Direct base calls, not cooperative super(): ImageEntity and
        # LissyDeviceInfo take different constructor arguments.
        ImageEntity.__init__(self, hass)
        LissyDeviceInfo.__init__(self, entry)
        self._attr_unique_id = _barcode_unique_id(entry)
        # The barcode is derived from static config data, so its content is
        # fixed from the moment the entity is created.
        self._attr_image_last_updated = dt_util.utcnow()
        self._barcode: bytes | None = None

    def image(self) -> bytes | None:
        """Return the barcode PNG, generating it once on first request."""
        if self._barcode is None:
            self._barcode = _generate_code39_png(self._entry.data["username"])
        return self._barcode
