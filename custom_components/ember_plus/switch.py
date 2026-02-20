"""Switch platform for the HA Ember+ integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_GPIS, CONF_IO_NAME, CONF_IO_NUMBER, DOMAIN
from .coordinator import EmberPlusCoordinator
from .entity import EmberPlusEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Ember+ GPI switches from a config entry."""
    coordinator: EmberPlusCoordinator = hass.data[DOMAIN][entry.entry_id]

    gpis: list[dict[str, Any]] = entry.options.get(
        CONF_GPIS, entry.data.get(CONF_GPIS, [])
    )

    entities = [
        EmberGPISwitch(
            coordinator=coordinator,
            io_number=int(gpi[CONF_IO_NUMBER]),
            io_name=gpi[CONF_IO_NAME],
        )
        for gpi in gpis
    ]

    async_add_entities(entities)


class EmberGPISwitch(EmberPlusEntity, SwitchEntity):
    """Represents a read/write GPI as a switch."""

    def __init__(
        self,
        coordinator: EmberPlusCoordinator,
        io_number: int,
        io_name: str,
    ) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, "gpi", io_number, io_name)

    @property
    def is_on(self) -> bool | None:
        """Return True if the GPI is active."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("gpi", {}).get(self._io_number)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the GPI on."""
        await self.coordinator.client.set_gpi_state(self._io_number, True)
        self.coordinator.data.setdefault("gpi", {})[self._io_number] = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the GPI off."""
        await self.coordinator.client.set_gpi_state(self._io_number, False)
        self.coordinator.data.setdefault("gpi", {})[self._io_number] = False
        self.async_write_ha_state()
