"""Config flow for Lissy."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import probatio
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import LissyAuthError, LissyClient, LissyConnectionError
from .const import CONF_SHOW_BARCODE, DEFAULT_SHOW_BARCODE, DOMAIN, URL_SUFFIX
from .libraries import (
    LIBRARIES,
    MANUAL_SLUG,
    SELECT_OPTIONS,
    library_for_url,
    normalize_portal_url,
)

_STEP_USER_SCHEMA = probatio.Schema(
    {
        probatio.Required("library"): SelectSelector(
            SelectSelectorConfig(
                options=SELECT_OPTIONS,
                translation_key="library",
                mode=SelectSelectorMode.DROPDOWN,
                sort=False,
            )
        )
    }
)

_STEP_MANUAL_SCHEMA = probatio.Schema(
    {
        probatio.Required("base_url"): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        )
    }
)

_STEP_LOGIN_SCHEMA = probatio.Schema(
    {
        probatio.Required("username"): str,
        probatio.Required("password"): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
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

    def __init__(self) -> None:
        """Initialize flow state.

        In-progress config flows are not persisted across HA restarts, so a
        plain attribute is sufficient to carry the chosen base URL between
        the selection and login steps.
        """
        self._base_url: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> LissyOptionsFlow:
        """Create the options flow handler."""
        return LissyOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            slug = user_input["library"]
            if slug == MANUAL_SLUG:
                return await self.async_step_manual()
            library = LIBRARIES.get(slug)
            if library is None:
                # Unreachable through the selector's own validation.
                errors = {"library": "unknown_library"}
            else:
                self._base_url = library["url"]
                return await self.async_step_login()

        return self.async_show_form(
            step_id="user", data_schema=_STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the portal URL when the library is not in the dropdown."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input["base_url"].rstrip("/").endswith(URL_SUFFIX):
                errors = {"base_url": "invalid_url"}
            else:
                self._base_url = user_input["base_url"]
                return await self.async_step_login()

        return self.async_show_form(
            step_id="manual", data_schema=_STEP_MANUAL_SCHEMA, errors=errors
        )

    async def async_step_login(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            base_url = self._base_url
            if base_url is None:
                # Defensive: unreachable through the normal step sequence —
                # login is only entered after user/manual set the base URL.
                return await self.async_step_user()
            user_input["username"] = user_input["username"].strip()
            merged = {**user_input, "base_url": base_url}
            errors = await _validate_credentials(self.hass, merged)
            if not errors:
                # ``<username>@<host><path>``: one card number may exist at
                # two portals (and at two biblis.de-hosted ones that differ
                # only in path), and HA never rewrites a configured entry's
                # unique id, so new entries must discriminate on host AND
                # path. Scheme and trailing slash are normalized away so
                # spelling drift does not spawn a duplicate of the same
                # account.
                username = user_input["username"]
                normalized = normalize_portal_url(base_url)
                await self.async_set_unique_id(f"{username}@{normalized}")
                self._abort_if_unique_id_configured()
                # Entries created before multi-library support keep their
                # username-only (and later username@host) unique ids — match
                # them on their data instead of treating a re-add as a new
                # account.
                for entry in self.hass.config_entries.async_entries(DOMAIN):
                    if entry.data.get("username") != username:
                        continue
                    if (
                        normalize_portal_url(entry.data.get("base_url", ""))
                        == normalized
                    ):
                        return self.async_abort(reason="already_configured")
                title: str = (
                    f"{name} ({username})"
                    if (name := library_for_url(base_url))
                    else f"Lissy ({username})"
                )
                return self.async_create_entry(title=title, data=merged)

        return self.async_show_form(
            step_id="login", data_schema=_STEP_LOGIN_SCHEMA, errors=errors
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
                from .image import code39_value, resolve_card_number

                if code39_value(resolve_card_number(self.config_entry)) is None:
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
