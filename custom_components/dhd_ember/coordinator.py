"""DataUpdateCoordinator for the HA DHD Ember+ integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import CONF_GPIS, CONF_GPOS, CONF_IO_NUMBER, DOMAIN
from .ember import EmberClient, EmberConnectionError

_LOGGER = logging.getLogger(__name__)


class DHDEmberCoordinator(DataUpdateCoordinator[dict[str, dict[int, bool]]]):
    """Coordinator that receives push updates from a DHD mixer via Ember+.

    Data structure: {"gpi": {1: True, 2: False, ...}, "gpo": {1: False, ...}}
    No periodic polling — the mixer pushes all changes instantly.
    """

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: EmberClient,
        entry: ConfigEntry,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,
        )
        self.client = client
        self.config_entry = entry

        # Register the push callback on the Ember+ client.
        self.client.set_state_callback(self._handle_push)

    def _get_configured_ios(self) -> dict[str, list[int]]:
        """Return configured GPI and GPO numbers from config entry."""
        gpis_conf: list[dict[str, Any]] = self.config_entry.options.get(
            CONF_GPIS,
            self.config_entry.data.get(CONF_GPIS, []),
        )
        gpos_conf: list[dict[str, Any]] = self.config_entry.options.get(
            CONF_GPOS,
            self.config_entry.data.get(CONF_GPOS, []),
        )
        return {
            "gpi": [int(g[CONF_IO_NUMBER]) for g in gpis_conf],
            "gpo": [int(g[CONF_IO_NUMBER]) for g in gpos_conf],
        }

    @callback
    def _handle_push(self, io_type: str, number: int, state: bool) -> None:
        """Handle an unsolicited state change from the mixer."""
        configured = self._get_configured_ios()
        if number not in configured.get(io_type, []):
            return

        if self.data is None:
            self.data = {"gpi": {}, "gpo": {}}

        if self.data.get(io_type, {}).get(number) == state:
            return

        _LOGGER.debug(
            "Instant update: %s %d → %s", io_type, number, state,
        )
        self.data.setdefault(io_type, {})[number] = state
        self.async_set_updated_data(self.data)

    async def _async_update_data(self) -> dict[str, dict[int, bool]]:
        """Fetch the current state of all configured GPIs and GPOs."""
        configured = self._get_configured_ios()

        states: dict[str, dict[int, bool]] = {"gpi": {}, "gpo": {}}

        try:
            for num in configured["gpi"]:
                states["gpi"][num] = self.client.gpi_states.get(num, False)
            for num in configured["gpo"]:
                states["gpo"][num] = self.client.gpo_states.get(num, False)
        except EmberConnectionError as err:
            await self.client.disconnect()
            raise UpdateFailed(
                f"Lost connection to DHD mixer: {err}"
            ) from err

        return states
