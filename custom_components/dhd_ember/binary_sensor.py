"""Binary sensor platform for the HA DHD Ember+ integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_GPOS, CONF_IO_NAME, CONF_IO_NUMBER, DOMAIN
from .coordinator import DHDEmberCoordinator
from .entity import DHDEmberEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DHD Ember+ GPO binary sensors from a config entry."""
    coordinator: DHDEmberCoordinator = hass.data[DOMAIN][entry.entry_id]

    gpos: list[dict[str, Any]] = entry.options.get(
        CONF_GPOS, entry.data.get(CONF_GPOS, [])
    )

    entities = [
        DHDGPOBinarySensor(
            coordinator=coordinator,
            io_number=int(gpo[CONF_IO_NUMBER]),
            io_name=gpo[CONF_IO_NAME],
        )
        for gpo in gpos
    ]

    async_add_entities(entities)


class DHDGPOBinarySensor(DHDEmberEntity, BinarySensorEntity):
    """Represents a read-only DHD GPO as a binary sensor."""

    def __init__(
        self,
        coordinator: DHDEmberCoordinator,
        io_number: int,
        io_name: str,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, "gpo", io_number, io_name)

    @property
    def is_on(self) -> bool | None:
        """Return True if the GPO is active."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("gpo", {}).get(self._io_number)
