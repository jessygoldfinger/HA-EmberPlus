"""Number platform for the HA EmberPlus integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity
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
    """Set up Ember+ integer numbers from a config entry."""
    coordinator: EmberPlusCoordinator = hass.data[DOMAIN][entry.entry_id]

    params_conf: list[dict[str, Any]] = entry.options.get(
        CONF_PARAMS, entry.data.get(CONF_PARAMS, [])
    )

    entities = []
    for p in params_conf:
        path_key = p[CONF_PATH_KEY]
        param = coordinator.client.parameters.get(path_key)
        if param is not None and param.value_type == "int":
            entities.append(
                EmberNumber(
                    coordinator=coordinator,
                    path_key=path_key,
                    label=p.get(CONF_PARAM_LABEL, param.label),
                    path=param.path,
                )
            )

    async_add_entities(entities)


class EmberNumber(EmberPlusEntity, NumberEntity):
    """Represents an integer Ember+ parameter as a number."""

    _attr_native_min_value = -32768
    _attr_native_max_value = 32767
    _attr_native_step = 1

    def __init__(
        self,
        coordinator: EmberPlusCoordinator,
        path_key: str,
        label: str,
        path: list[int],
    ) -> None:
        """Initialise the number."""
        super().__init__(coordinator, path_key, label)
        self._path = path

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if self.coordinator.data is None:
            return None
        val = self.coordinator.data.get(self._path_key)
        return float(val) if val is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        int_val = int(value)
        await self.coordinator.client.set_value(self._path, int_val)
        if self.coordinator.data is not None:
            self.coordinator.data[self._path_key] = int_val
        self.async_write_ha_state()
