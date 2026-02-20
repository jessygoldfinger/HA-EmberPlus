"""DataUpdateCoordinator for the HA EmberPlus integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import CONF_PARAMS, CONF_PATH_KEY, DOMAIN
from .ember import EmberClient, EmberConnectionError

_LOGGER = logging.getLogger(__name__)

POLL_INTERVAL = timedelta(seconds=10)


class EmberPlusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that receives push updates via Ember+.

    Data structure: {"0.1.3": True, "0.3.0.2": -16000, ...}
    Keys are path_keys, values are the current parameter values.

    A 10-second poll interval ensures automatic reconnection when the
    device has been powered off and comes back online.
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
            update_interval=POLL_INTERVAL,
        )
        self.client = client
        self.config_entry = entry
        self._was_available = True

        # Build set of configured path_keys
        params_conf = entry.options.get(
            CONF_PARAMS, entry.data.get(CONF_PARAMS, [])
        )
        self._configured_keys: set[str] = {
            p[CONF_PATH_KEY] for p in params_conf
        }

        # Register push callback
        self.client.set_state_callback(self._on_state_change)

    @callback
    def _on_state_change(self, path_key: str, value: Any) -> None:
        """Handle a push update from the Ember+ client."""
        if path_key in self._configured_keys:
            self.async_set_updated_data(self._build_data())

    def _build_data(self) -> dict[str, Any]:
        """Build the data dict from current client states."""
        result: dict[str, Any] = {}
        for pk in self._configured_keys:
            param = self.client.parameters.get(pk)
            if param is not None:
                result[pk] = param.value
        return result

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest data.

        Called every 10 seconds.  If the connection is down, attempts
        to reconnect silently.  Only logs once on disconnect and once
        on reconnect to avoid flooding the log during long outages.
        """
        # Reconnect if the connection was lost.
        if not self.client.connected:
            if self._was_available:
                _LOGGER.warning(
                    "Ember+ device disconnected, will retry silently"
                )
                self._was_available = False

            try:
                await self.client.disconnect()
                await self.client.connect()
                await self.client.discover()
                await self.client.subscribe_all()
            except (EmberConnectionError, OSError, TimeoutError):
                # Silently retry on next poll — no log spam.
                return self.data or {}

            # Reconnected!
            self._was_available = True
            _LOGGER.info("Reconnected to Ember+ device")

        data = self._build_data()

        if not self._was_available and data:
            self._was_available = True
            _LOGGER.info("Ember+ device connection restored")

        return data
