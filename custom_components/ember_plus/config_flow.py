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
    CONF_PARAMS,
    CONF_PARAM_LABEL,
    CONF_PATH_KEY,
    DEFAULT_PORT,
    DOMAIN,
)
from .ember import EmberClient, EmberConnectionError, EmberParam

_LOGGER = logging.getLogger(__name__)


def _build_param_options(
    params: dict[str, EmberParam],
    node_labels: dict[str, str],
) -> dict[str, str]:
    """Build a {path_key: display_label} dict for multi_select.

    Groups parameters under their parent node label for clarity.
    Skips parameters with unknown/None values.
    """
    options: dict[str, str] = {}
    for pk in sorted(params.keys()):
        p = params[pk]
        if p.value is None:
            continue
        # Find parent node label
        parts = pk.rsplit(".", 1)
        parent_key = parts[0] if len(parts) > 1 else ""
        parent_label = node_labels.get(parent_key, "")
        if parent_label:
            display = f"{parent_label} > {p.label}"
        else:
            display = p.label
        options[pk] = display
    return options


class EmberPlusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HA Ember+.

    Step 1: IP + port
    Step 2: Auto-discover all parameters, let user select
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the config flow."""
        self._host: str = ""
        self._port: int = DEFAULT_PORT
        self._discovered: dict[str, EmberParam] = {}
        self._node_labels: dict[str, str] = {}

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
                self._discovered = client.parameters
                self._node_labels = client.node_labels
                await client.disconnect()

                if self._discovered:
                    return await self.async_step_select_params()

                return self.async_create_entry(
                    title=f"Ember+ ({self._host})",
                    data={
                        CONF_HOST: self._host,
                        CONF_PORT: self._port,
                        CONF_PARAMS: [],
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

    async def async_step_select_params(
        self, user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Let the user select which parameters to add."""
        options = _build_param_options(self._discovered, self._node_labels)

        if user_input is not None:
            selected = user_input.get("params", [])
            params = [
                {
                    CONF_PATH_KEY: pk,
                    CONF_PARAM_LABEL: options.get(pk, pk),
                }
                for pk in selected
            ]
            return self.async_create_entry(
                title=f"Ember+ ({self._host})",
                data={
                    CONF_HOST: self._host,
                    CONF_PORT: self._port,
                    CONF_PARAMS: params,
                },
            )

        schema_fields: dict[Any, Any] = {}
        if options:
            schema_fields[
                vol.Optional("params", default=list(options.keys()))
            ] = cv.multi_select(options)

        return self.async_show_form(
            step_id="select_params",
            data_schema=vol.Schema(schema_fields),
            description_placeholders={
                "param_count": str(len(options)),
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
        self._available: dict[str, EmberParam] = {}
        self._node_labels: dict[str, str] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Scan the device and show all parameters for selection."""
        errors: dict[str, str] = {}

        # Scan the device tree
        if not self._available:
            host = self._config_entry.data[CONF_HOST]
            port = self._config_entry.data[CONF_PORT]

            client = EmberClient(host, port)
            try:
                await client.connect()
                await client.discover()
                self._available = client.parameters
                self._node_labels = client.node_labels
                await client.disconnect()
            except (EmberConnectionError, OSError, TimeoutError):
                errors["base"] = "cannot_connect"
                return self.async_show_form(
                    step_id="init",
                    data_schema=vol.Schema({}),
                    errors=errors,
                )

        options = _build_param_options(self._available, self._node_labels)

        if user_input is not None:
            selected = user_input.get("params", [])
            params = [
                {
                    CONF_PATH_KEY: pk,
                    CONF_PARAM_LABEL: options.get(pk, pk),
                }
                for pk in selected
            ]
            return self.async_create_entry(
                title="",
                data={CONF_PARAMS: params},
            )

        # Currently configured path_keys
        current_conf: list[dict[str, Any]] = self._config_entry.options.get(
            CONF_PARAMS, self._config_entry.data.get(CONF_PARAMS, []),
        )
        current_keys = [p[CONF_PATH_KEY] for p in current_conf]

        schema_fields: dict[Any, Any] = {}
        if options:
            schema_fields[
                vol.Optional("params", default=current_keys)
            ] = cv.multi_select(options)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_fields),
            description_placeholders={
                "param_count": str(len(options)),
            },
        )
