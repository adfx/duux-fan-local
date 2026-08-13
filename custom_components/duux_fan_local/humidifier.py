"""
Humidifier platform for the Duux Fan Local integration.
Provides local control of Duux dehumidifiers over MQTT.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.humidifier import (
    HumidifierEntity,
    HumidifierDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MANUFACTURER, MODELS
from .devices import DEVICE_PROFILES
from .mqtt import DuuxMqttClient


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Duux dehumidifier entities from a config entry."""

    client: DuuxMqttClient = hass.data[DOMAIN][config_entry.entry_id]

    device_id = config_entry.data["device_id"]
    base_name = config_entry.data["name"]
    model = config_entry.data.get("model", "whisper_flex_2")

    profile = DEVICE_PROFILES.get(model)

    if not profile or "humidifier" not in profile:
        return

    async_add_entities(
        [
            DuuxDehumidifier(
                client=client,
                device_id=device_id,
                base_name=base_name,
                model=model,
                details=profile["humidifier"],
            )
        ]
    )


class DuuxDehumidifier(HumidifierEntity):
    """Representation of a Duux dehumidifier."""

    _attr_should_poll = False
    _attr_device_class = HumidifierDeviceClass.DEHUMIDIFIER

    def __init__(
        self,
        client: DuuxMqttClient,
        device_id: str,
        base_name: str,
        model: str,
        details: dict[str, Any],
    ) -> None:
        """Initialize the dehumidifier."""

        self._client = client
        self._device_id = device_id
        self._name = base_name
        self._model = model
        self._details = details

        self._attr_name = base_name
        self._attr_unique_id = f"{DOMAIN}_{device_id}_humidifier"

        self._attr_is_on = False
        self._attr_target_humidity = None
        self._current_humidity = None

        self._attr_min_humidity = float(details.get("min_humidity", 30))
        self._attr_max_humidity = float(details.get("max_humidity", 80))

        self._humidity_step = int(details.get("humidity_step", 5))

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""

        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._name,
            "manufacturer": MANUFACTURER,
            "model": MODELS.get(self._model, self._model),
            "connections": {("mac", self._device_id)},
        }

    @property
    def current_humidity(self) -> float | None:
        """Return current humidity."""

        return self._current_humidity

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the dehumidifier on."""

        await self.hass.async_add_executor_job(
            self._client.publish,
            "tune set power 1",
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the dehumidifier off."""

        await self.hass.async_add_executor_job(
            self._client.publish,
            "tune set power 0",
        )

    async def async_set_humidity(self, humidity: int) -> None:
        """Set target humidity."""

        humidity = round(humidity / self._humidity_step) * self._humidity_step

        humidity = max(
            int(self._attr_min_humidity),
            min(int(self._attr_max_humidity), humidity),
        )

        await self.hass.async_add_executor_job(
            self._client.publish,
            f"tune set sp {humidity}",
        )

    @callback
    def _update_state(self, fan_data: dict[str, Any]) -> None:
        """Update state from MQTT payload."""

        power_key = self._details.get("power_key", "power")
        target_key = self._details.get("target_humidity_key", "sp")
        current_key = self._details.get("current_humidity_key", "hum")

        power = fan_data.get(power_key)
        target = fan_data.get(target_key)
        current = fan_data.get(current_key)

        if power is not None:
            self._attr_is_on = power == 1

        if target is not None:
            self._attr_target_humidity = int(target)

        if current is not None:
            self._current_humidity = float(current)

        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register MQTT callback."""

        self._client.register_callback(self._update_state)

    async def async_will_remove_from_hass(self) -> None:
        """Remove MQTT callback."""

        self._client.unregister_callback(self._update_state)
