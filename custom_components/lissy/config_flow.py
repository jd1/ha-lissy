"""Config flow for Lissy."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import DEFAULT_BASE_URL, LissyAuthError, LissyClient, LissyConnectionError
from .const import DOMAIN

STEP_SCHEMA = vol.Schema(
    {
        vol.Required("username"): str,
        vol.Required("password"): str,
        vol.Optional("base_url", default=DEFAULT_BASE_URL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
    }
)


async def _validate(user_input: dict[str, Any]) -> str | None:
    """Return an error key, or None if the credentials work."""
    client = LissyClient(
        user_input["username"],
        user_input["password"],
        user_input.get("base_url", DEFAULT_BASE_URL),
    )
    try:
        await client.list_loans()
    except LissyAuthError:
        return "invalid_auth"
    except LissyConnectionError:
        return "cannot_connect"
    return None


class LissyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input["username"] = user_input["username"].strip()
            error = await _validate(user_input)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(user_input["username"])
                self._abort_if_unique_id_configured()
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
            error = await _validate(merged)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(reauth_entry.unique_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(reauth_entry, data=merged)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("password"): str}),
            errors=errors,
        )
