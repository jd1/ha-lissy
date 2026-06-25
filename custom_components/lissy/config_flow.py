"""Config flow for Lissy."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .api import DEFAULT_BASE_URL, LissyAuthError, LissyClient, LissyConnectionError
from .const import DOMAIN

STEP_SCHEMA = vol.Schema(
    {
        vol.Required("username"): str,
        vol.Required("password"): str,
        vol.Optional("base_url", default=DEFAULT_BASE_URL): str,
    }
)


class LissyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = LissyClient(
                user_input["username"],
                user_input["password"],
                user_input.get("base_url", DEFAULT_BASE_URL),
            )
            try:
                await client.list_loans()
            except LissyAuthError:
                errors["base"] = "invalid_auth"
            except LissyConnectionError:
                errors["base"] = "cannot_connect"
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
