"""Sensor platform for the HA EmberPlus integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
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
    """Set up Ember+ string sensors from a config entry."""
    coordinator: EmberPlusCoordinator = hass.data[DOMAIN][entry.entry_id]

    params_conf: list[dict[str, Any]] = entry.options.get(
        CONF_PARAMS, entry.data.get(CONF_PARAMS, [])
    )

    entities = []
    for p in params_conf:
        path_key = p[CONF_PATH_KEY]
        param = coordinator.client.parameters.get(path_key)
        if param is not None and param.value_type == "str":
            entities.append(
                EmberSensor(
                    coordinator=coordinator,
                    path_key=path_key,
                    label=p.get(CONF_PARAM_LABEL, param.label),
                )
            )

    async_add_entities(entities)


class EmberSensor(EmberPlusEntity, SensorEntity):
    """Represents a string Ember+ parameter as a sensor."""

    def __init__(
        self,
        coordinator: EmberPlusCoordinator,
        path_key: str,
        label: str,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, path_key, label)

    @property
    def native_value(self) -> str | None:
        """Return the current value."""
        if self.coordinator.data is None:
            return None
        val = self.coordinator.data.get(self._path_key)
        return str(val) if val is not None else None
