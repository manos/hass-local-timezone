"""Sensor platform for Local Timezone integration."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path

from tzfpy import get_tz

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_LATITUDE_ENTITY, CONF_LONGITUDE_ENTITY, CONF_SET_HA_TIMEZONE, DOMAIN

_LOGGER = logging.getLogger(__name__)


SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key="timezone",
        name="Timezone",
        icon="mdi:map-clock",
    ),
    SensorEntityDescription(
        key="timezone_abbreviation",
        name="Timezone Abbreviation",
        icon="mdi:clock-outline",
    ),
    SensorEntityDescription(
        key="utc_offset",
        name="UTC Offset",
        icon="mdi:clock-plus-outline",
    ),
    SensorEntityDescription(
        key="dst_active",
        name="DST Active",
        icon="mdi:weather-sunny-alert",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Local Timezone sensors from a config entry."""
    lat_entity = entry.data[CONF_LATITUDE_ENTITY]
    lon_entity = entry.data[CONF_LONGITUDE_ENTITY]

    set_ha_tz = entry.data.get(CONF_SET_HA_TIMEZONE, True)

    entities = [
        LocalTimezoneSensor(entry, description, lat_entity, lon_entity, set_ha_tz)
        for description in SENSOR_DESCRIPTIONS
    ]

    async_add_entities(entities, update_before_add=True)


class LocalTimezoneSensor(SensorEntity):
    """Sensor that provides timezone information from GPS coordinates."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        entry: ConfigEntry,
        description: SensorEntityDescription,
        lat_entity: str,
        lon_entity: str,
        set_ha_tz: bool = True,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        self._entry = entry
        self._lat_entity = lat_entity
        self._lon_entity = lon_entity
        self._set_ha_tz = set_ha_tz
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._tz_name: str | None = None
        self._unsub: callback | None = None

    async def async_added_to_hass(self) -> None:
        """Register state change listeners when added to hass."""
        self._unsub = async_track_state_change_event(
            self.hass,
            [self._lat_entity, self._lon_entity],
            self._async_sensor_changed,
        )
        # Initial update
        await self._async_update_timezone()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up on removal."""
        if self._unsub:
            self._unsub()

    @callback
    def _async_sensor_changed(self, event) -> None:
        """Handle source sensor state changes."""
        self.hass.async_create_task(self._async_update_timezone())

    async def _async_update_timezone(self) -> None:
        """Update timezone from current coordinates."""
        lat_state = self.hass.states.get(self._lat_entity)
        lon_state = self.hass.states.get(self._lon_entity)

        if lat_state is None or lon_state is None:
            _LOGGER.warning("GPS entity not available yet")
            return

        try:
            lat = float(lat_state.state)
            lon = float(lon_state.state)
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Invalid GPS coordinates: lat=%s, lon=%s",
                lat_state.state,
                lon_state.state,
            )
            return

        # Run timezone lookup in executor (CPU-bound)
        tz_name = await self.hass.async_add_executor_job(
            _lookup_timezone, lat, lon
        )

        if tz_name is None:
            _LOGGER.warning(
                "Could not determine timezone for %s, %s", lat, lon
            )
            return

        old_tz = self._tz_name
        self._tz_name = tz_name
        self._update_state()
        self.async_write_ha_state()

        # Write timezone to file for host-side consumption
        if self.entity_description.key == "timezone":
            await self.hass.async_add_executor_job(
                _write_timezone_file, self.hass.config.config_dir, tz_name
            )

        # Auto-update HASS core timezone when it changes
        if (
            self._set_ha_tz
            and self.entity_description.key == "timezone"
            and tz_name != old_tz
            and old_tz is not None  # Skip initial load
        ):
            await self._async_set_ha_timezone(tz_name)

    async def _async_set_ha_timezone(self, tz_name: str) -> None:
        """Update Home Assistant's core timezone configuration."""
        _LOGGER.info(
            "Updating Home Assistant timezone to %s", tz_name
        )
        await self.hass.config.async_update(time_zone=tz_name)

    def _update_state(self) -> None:
        """Update sensor state based on current timezone."""
        if self._tz_name is None:
            self._attr_native_value = None
            return

        import zoneinfo

        try:
            tz = zoneinfo.ZoneInfo(self._tz_name)
        except (KeyError, zoneinfo.ZoneInfoNotFoundError):
            _LOGGER.error("Unknown timezone: %s", self._tz_name)
            self._attr_native_value = None
            return

        now = datetime.now(tz)
        utc_offset = now.utcoffset()
        dst = now.dst()

        key = self.entity_description.key

        if key == "timezone":
            self._attr_native_value = self._tz_name
        elif key == "timezone_abbreviation":
            self._attr_native_value = now.strftime("%Z")
        elif key == "utc_offset":
            if utc_offset is not None:
                total_hours = utc_offset.total_seconds() / 3600
                sign = "+" if total_hours >= 0 else ""
                if total_hours == int(total_hours):
                    self._attr_native_value = f"UTC{sign}{int(total_hours)}"
                else:
                    hours = int(total_hours)
                    minutes = int(abs(total_hours - hours) * 60)
                    self._attr_native_value = (
                        f"UTC{sign}{hours}:{minutes:02d}"
                    )
            else:
                self._attr_native_value = None
        elif key == "dst_active":
            self._attr_native_value = (
                "on" if (dst is not None and dst.total_seconds() > 0) else "off"
            )


def _write_timezone_file(config_dir: str, tz_name: str) -> None:
    """Write current timezone to a file for host-side scripts."""
    try:
        tz_file = Path(config_dir) / ".local_timezone"
        tz_file.write_text(tz_name + "\n")
    except OSError:
        _LOGGER.warning("Could not write timezone file to %s", config_dir)


def _lookup_timezone(lat: float, lon: float) -> str | None:
    """Look up timezone name from coordinates (runs in executor)."""
    result = get_tz(lon, lat)
    return result if result else None
