"""Base entity for the HA Ember+ integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EmberPlusCoordinator


class EmberPlusEntity(CoordinatorEntity[EmberPlusCoordinator]):
    """Base class for Ember+ entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EmberPlusCoordinator,
        io_type: str,
        io_number: int,
        io_name: str,
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._io_type = io_type
        self._io_number = io_number
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{io_type}_{io_number}"
        )
        self._attr_name = io_name

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the Ember+ device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name=self.coordinator.config_entry.title,
            manufacturer="Jessy Goldfinger",
            model="HA Ember+ integration",
            configuration_url=(
                f"http://{self.coordinator.client.host}"
            ),
        )

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return (
            super().available
            and self.coordinator.client.connected
            and self.coordinator.data is not None
            and self._io_number
            in (self.coordinator.data.get(self._io_type) or {})
        )
