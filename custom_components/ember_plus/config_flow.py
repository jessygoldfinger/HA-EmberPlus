"""Config flow for the HA Ember+ integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_GPIS,
    CONF_GPOS,
    CONF_IO_NAME,
    CONF_IO_NUMBER,
    DEFAULT_PORT,
    DOMAIN,
)
from .ember import EmberClient, EmberConnectionError

_LOGGER = logging.getLogger(__name__)


class EmberPlusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HA Ember+.

    Step 1: IP + port
    Step 2: Auto-discover GPIs/GPOs, let user select which to add
    Done.  More can be added via Options.
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the config flow."""
        self._host: str = ""
        self._port: int = DEFAULT_PORT
        self._discovered_gpis: dict[int, str] = {}
        self._discovered_gpos: dict[int, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle connection setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._host = user_input[CONF_HOST]
            self._port = user_input[CONF_PORT]

            self._async_abort_entries_match({CONF_HOST: self._host})

            client = EmberClient(self._host, self._port)
            try:
                await client.connect()
                await client.discover()
            except (EmberConnectionError, OSError, TimeoutError):
                errors["base"] = "cannot_connect"
            else:
                self._discovered_gpis = client.gpi_labels
                self._discovered_gpos = client.gpo_labels
                await client.disconnect()

                if self._discovered_gpis or self._discovered_gpos:
                    return await self.async_step_select_ios()

                return self.async_create_entry(
                    title=f"Ember+ ({self._host})",
                    data={
                        CONF_HOST: self._host,
                        CONF_PORT: self._port,
                        CONF_GPIS: [],
                        CONF_GPOS: [],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                }
            ),
            errors=errors,
        )

    async def async_step_select_ios(
        self, user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Let the user select which GPIs and GPOs to add."""
        if user_input is not None:
            selected_gpis = [int(n) for n in user_input.get("gpis", [])]
            selected_gpos = [int(n) for n in user_input.get("gpos", [])]

            gpis = [
                {
                    CONF_IO_NUMBER: num,
                    CONF_IO_NAME: self._discovered_gpis.get(num, f"GPI {num}"),
                }
                for num in selected_gpis
            ]
            gpos = [
                {
                    CONF_IO_NUMBER: num,
                    CONF_IO_NAME: self._discovered_gpos.get(num, f"GPO {num}"),
                }
                for num in selected_gpos
            ]

            return self.async_create_entry(
                title=f"Ember+ ({self._host})",
                data={
                    CONF_HOST: self._host,
                    CONF_PORT: self._port,
                    CONF_GPIS: gpis,
                    CONF_GPOS: gpos,
                },
            )

        schema_fields: dict[Any, Any] = {}

        if self._discovered_gpis:
            gpi_options = {
                str(num): label
                for num, label in sorted(self._discovered_gpis.items())
            }
            schema_fields[
                vol.Optional("gpis", default=list(gpi_options.keys()))
            ] = cv.multi_select(gpi_options)

        if self._discovered_gpos:
            gpo_options = {
                str(num): label
                for num, label in sorted(self._discovered_gpos.items())
            }
            schema_fields[
                vol.Optional("gpos", default=list(gpo_options.keys()))
            ] = cv.multi_select(gpo_options)

        return self.async_show_form(
            step_id="select_ios",
            data_schema=vol.Schema(schema_fields),
            description_placeholders={
                "gpi_count": str(len(self._discovered_gpis)),
                "gpo_count": str(len(self._discovered_gpos)),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> EmberPlusOptionsFlow:
        """Return the options flow handler."""
        return EmberPlusOptionsFlow(config_entry)


class EmberPlusOptionsFlow(config_entries.OptionsFlow):
    """Handle options for HA Ember+."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialise the options flow."""
        self._config_entry = config_entry
        self._available_gpis: dict[int, str] = {}
        self._available_gpos: dict[int, str] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Scan the mixer and show all GPIs/GPOs for selection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_gpis = [int(n) for n in user_input.get("gpis", [])]
            selected_gpos = [int(n) for n in user_input.get("gpos", [])]

            gpis = [
                {
                    CONF_IO_NUMBER: num,
                    CONF_IO_NAME: self._available_gpis.get(num, f"GPI {num}"),
                }
                for num in selected_gpis
            ]
            gpos = [
                {
                    CONF_IO_NUMBER: num,
                    CONF_IO_NAME: self._available_gpos.get(num, f"GPO {num}"),
                }
                for num in selected_gpos
            ]

            return self.async_create_entry(
                title="",
                data={CONF_GPIS: gpis, CONF_GPOS: gpos},
            )

        # Scan the mixer tree
        host = self._config_entry.data[CONF_HOST]
        port = self._config_entry.data[CONF_PORT]

        client = EmberClient(host, port)
        try:
            await client.connect()
            await client.discover()
            self._available_gpis = client.gpi_labels
            self._available_gpos = client.gpo_labels
            await client.disconnect()
        except (EmberConnectionError, OSError, TimeoutError):
            errors["base"] = "cannot_connect"
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        # Currently configured numbers
        gpis_conf: list[dict[str, Any]] = self._config_entry.options.get(
            CONF_GPIS, self._config_entry.data.get(CONF_GPIS, []),
        )
        gpos_conf: list[dict[str, Any]] = self._config_entry.options.get(
            CONF_GPOS, self._config_entry.data.get(CONF_GPOS, []),
        )
        current_gpi_nums = {int(g[CONF_IO_NUMBER]) for g in gpis_conf}
        current_gpo_nums = {int(g[CONF_IO_NUMBER]) for g in gpos_conf}

        schema_fields: dict[Any, Any] = {}

        if self._available_gpis:
            gpi_options = {
                str(num): label
                for num, label in sorted(self._available_gpis.items())
            }
            schema_fields[
                vol.Optional(
                    "gpis",
                    default=[str(n) for n in sorted(current_gpi_nums)],
                )
            ] = cv.multi_select(gpi_options)

        if self._available_gpos:
            gpo_options = {
                str(num): label
                for num, label in sorted(self._available_gpos.items())
            }
            schema_fields[
                vol.Optional(
                    "gpos",
                    default=[str(n) for n in sorted(current_gpo_nums)],
                )
            ] = cv.multi_select(gpo_options)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_fields),
            description_placeholders={
                "gpi_count": str(len(self._available_gpis)),
                "gpo_count": str(len(self._available_gpos)),
            },
        )
