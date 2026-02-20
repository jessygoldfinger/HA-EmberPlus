"""Switch platform for the HA EmberPlus integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_PARAMS, CONF_PARAM_LABEL, CONF_PATH_KEY, DOMAIN
from .coordinator import EmberPlusCoordinator
from .entity import EmberPlusEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Ember+ boolean switches from a config entry."""
    coordinator: EmberPlusCoordinator = hass.data[DOMAIN][entry.entry_id]

    params_conf: list[dict[str, Any]] = entry.options.get(
        CONF_PARAMS, entry.data.get(CONF_PARAMS, [])
    )

    entities = []
    for p in params_conf:
        path_key = p[CONF_PATH_KEY]
        param = coordinator.client.parameters.get(path_key)
        if param is not None and param.value_type == "bool":
            entities.append(
                EmberSwitch(
                    coordinator=coordinator,
                    path_key=path_key,
                    label=p.get(CONF_PARAM_LABEL, param.label),
                    path=param.path,
                )
            )

    async_add_entities(entities)


class EmberSwitch(EmberPlusEntity, SwitchEntity):
    """Represents a boolean Ember+ parameter as a switch."""

    def __init__(
        self,
        coordinator: EmberPlusCoordinator,
        path_key: str,
        label: str,
        path: list[int],
    ) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, path_key, label)
        self._path = path

    @property
    def is_on(self) -> bool | None:
        """Return True if the parameter is active."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._path_key)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on."""
        await self.coordinator.client.set_value(self._path, True)
        if self.coordinator.data is not None:
            self.coordinator.data[self._path_key] = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        await self.coordinator.client.set_value(self._path, False)
        if self.coordinator.data is not None:
            self.coordinator.data[self._path_key] = False
        self.async_write_ha_state()
