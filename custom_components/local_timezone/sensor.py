"""Sensor platform for Local Timezone integration."""

from __future__ import annotations

from datetime import datetime, timezone
import logging

from timezonefinder import TimezoneFinder

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_LATITUDE_ENTITY, CONF_LONGITUDE_ENTITY, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Initialize TimezoneFinder once (it loads ~40MB of polygon data)
_TZ_FINDER: TimezoneFinder | None = None


def _get_timezone_finder() -> TimezoneFinder:
    """Get or create the TimezoneFinder instance."""
    global _TZ_FINDER  # noqa: PLW0603
    if _TZ_FINDER is None:
        _TZ_FINDER = TimezoneFinder()
    return _TZ_FINDER


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

    # Initialize TimezoneFinder in executor (blocks on first load)
    await hass.async_add_executor_job(_get_timezone_finder)

    entities = [
        LocalTimezoneSensor(entry, description, lat_entity, lon_entity)
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
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        self._entry = entry
        self._lat_entity = lat_entity
        self._lon_entity = lon_entity
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

        self._tz_name = tz_name
        self._update_state()
        self.async_write_ha_state()

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


def _lookup_timezone(lat: float, lon: float) -> str | None:
    """Look up timezone name from coordinates (runs in executor)."""
    tf = _get_timezone_finder()
    return tf.timezone_at(lng=lon, lat=lat)
