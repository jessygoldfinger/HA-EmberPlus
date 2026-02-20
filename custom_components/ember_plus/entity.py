"""Base entity for the HA EmberPlus integration."""

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
        path_key: str,
        label: str,
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._path_key = path_key
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{path_key}"
        )
        self._attr_name = label

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the Ember+ device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name=self.coordinator.config_entry.title,
            manufacturer="Jessy Goldfinger",
            model="HA EmberPlus",
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
            and self._path_key in self.coordinator.data
        )
