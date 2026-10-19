"""Config flow for Lissy."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import probatio
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import LissyAuthError, LissyClient, LissyConnectionError
from .const import CONF_SHOW_BARCODE, DEFAULT_SHOW_BARCODE, DOMAIN

_URL_SUFFIX = "lissy/lissy.ly"


def _portal_host(base_url: str) -> str:
    """Return the portal host, falling back to the raw URL if unparseable."""
    return urlsplit(base_url).hostname or base_url


def _unique_id_for(username: str, base_url: str) -> str:
    """Return ``username@<portal host>``.

    The path is constant across every Lissy portal (the flow rejects any
    base_url not ending in ``lissy/lissy.ly``), so the host carries all
    the discrimination between libraries: the same card number may exist
    at two portals and must yield two entries.
    """
    return f"{username}@{_portal_host(base_url)}"


STEP_SCHEMA = probatio.Schema(
    {
        probatio.Required("username"): str,
        probatio.Required("password"): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        probatio.Required("base_url"): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
    }
)


async def _validate_credentials(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> dict[str, str]:
    """Return a form errors dict (field -> error key), empty if credentials work."""
    client = LissyClient(
        user_input["username"],
        user_input["password"],
        user_input["base_url"],
        session=async_get_clientsession(hass),
    )
    try:
        await client.list_loans()
    except LissyAuthError:
        return {"base": "invalid_auth"}
    except LissyConnectionError:
        return {"base": "cannot_connect"}
    return {}


class LissyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> LissyOptionsFlow:
        """Create the options flow handler."""
        return LissyOptionsFlow()

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input["username"] = user_input["username"].strip()
            if not user_input["base_url"].rstrip("/").endswith(_URL_SUFFIX):
                errors = {"base_url": "invalid_url"}
            else:
                errors = await _validate_credentials(self.hass, user_input)
            if not errors:
                await self.async_set_unique_id(
                    _unique_id_for(user_input["username"], user_input["base_url"])
                )
                self._abort_if_unique_id_configured()
                # Entries created before multi-library support keep their
                # username-only unique id — HA never rewrites a configured
                # entry's unique id — so match them on their data instead
                # of treating a re-add as a new account. Comparing portal
                # hosts rather than raw urls keeps spelling drift such as
                # a scheme change or trailing slash from spawning a
                # duplicate of the same account.
                username = user_input["username"]
                host = _portal_host(user_input["base_url"])
                for entry in self.hass.config_entries.async_entries(DOMAIN):
                    if entry.data.get("username") != username:
                        continue
                    if _portal_host(entry.data.get("base_url", "")) == host:
                        return self.async_abort(reason="already_configured")
                return self.async_create_entry(
                    title=f"Lissy ({user_input['username']})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            merged = {**reauth_entry.data, "password": user_input["password"]}
            errors = await _validate_credentials(self.hass, merged)
            if not errors:
                await self.async_set_unique_id(reauth_entry.unique_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(reauth_entry, data=merged)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=probatio.Schema(
                {
                    probatio.Required("password"): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
        )


def _options_schema(default: bool) -> probatio.Schema:
    """Schema for the options step with the current toggle value as default."""
    return probatio.Schema(
        {probatio.Required(CONF_SHOW_BARCODE, default=default): BooleanSelector()}
    )


class LissyOptionsFlow(config_entries.OptionsFlowWithReload):
    """Handle Lissy options; reloads the entry automatically on change."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            if user_input[CONF_SHOW_BARCODE]:
                # Local import keeps barcode/Pillow out of the config-flow
                # import path when the image platform isn't used.
                from .image import code39_value

                if code39_value(self.config_entry.data["username"]) is None:
                    return self.async_show_form(
                        step_id="init",
                        data_schema=_options_schema(
                            self.config_entry.options.get(
                                CONF_SHOW_BARCODE, DEFAULT_SHOW_BARCODE
                            )
                        ),
                        errors={"base": "barcode_unencodable"},
                    )
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(
                self.config_entry.options.get(CONF_SHOW_BARCODE, DEFAULT_SHOW_BARCODE)
            ),
        )
