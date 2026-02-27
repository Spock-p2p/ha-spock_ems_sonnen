"""Sensores para la integración Spock EMS Sonnen."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


@dataclass
class SpockSensorDescription:
    key: str
    name: str
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None


TELEMETRY_SENSORS: list[SpockSensorDescription] = [
    SpockSensorDescription("bat_soc", "Bateria SOC", PERCENTAGE, SensorDeviceClass.BATTERY, SensorStateClass.MEASUREMENT),
    SpockSensorDescription("bat_power", "Bateria Potencia", UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    SpockSensorDescription("pv_power", "PV Potencia", UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    SpockSensorDescription("ongrid_power", "Red Potencia (PCC)", UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    SpockSensorDescription("bat_capacity", "Capacidad Bateria (Wh)", None, None, None),
    SpockSensorDescription("bat_charge_allowed", "Bateria: Carga Permitida"),
    SpockSensorDescription("bat_discharge_allowed", "Bateria: Descarga Permitida"),
]

SPOCK_SENSORS: list[SpockSensorDescription] = [
    SpockSensorDescription("operation_mode", "Spock Modo"),
    SpockSensorDescription("status", "Spock Status"),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    entities: list[SensorEntity] = []

    for desc in TELEMETRY_SENSORS:
        entities.append(SpockTelemetrySensor(coordinator, entry, desc))

    for desc in SPOCK_SENSORS:
        entities.append(SpockAPISensor(coordinator, entry, desc))

    add_entities(entities)


class BaseSpockEntity(CoordinatorEntity):
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Spock EMS Sonnen",
            manufacturer="Spock",
            model="sonnenBatterie (API v2)",
        )


class SpockTelemetrySensor(BaseSpockEntity, SensorEntity):
    def __init__(self, coordinator, entry: ConfigEntry, desc: SpockSensorDescription) -> None:
        super().__init__(coordinator, entry)
        self._desc = desc
        self._attr_name = f"{self.device_info['name']} {desc.name}"
        self._attr_unique_id = f"{entry.entry_id}_telemetry_{desc.key}"
        self._attr_native_unit_of_measurement = desc.unit
        self._attr_device_class = desc.device_class
        self._attr_state_class = desc.state_class

    @property
    def native_value(self) -> Any:
        tel = (self.coordinator.data or {}).get("telemetry", {})
        return tel.get(self._desc.key)

    @property
    def available(self) -> bool:
        return isinstance((self.coordinator.data or {}).get("telemetry"), dict)


class SpockAPISensor(BaseSpockEntity, SensorEntity):
    def __init__(self, coordinator, entry: ConfigEntry, desc: SpockSensorDescription) -> None:
        super().__init__(coordinator, entry)
        self._desc = desc
        self._attr_name = f"{self.device_info['name']} {desc.name}"
        self._attr_unique_id = f"{entry.entry_id}_spock_{desc.key}"

    @property
    def native_value(self) -> Any:
        sp = (self.coordinator.data or {}).get("spock", {})
        return sp.get(self._desc.key)

    @property
    def available(self) -> bool:
        return isinstance((self.coordinator.data or {}).get("spock"), dict)
