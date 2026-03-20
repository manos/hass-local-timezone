"""Config flow for Local Timezone integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import CONF_LATITUDE_ENTITY, CONF_LONGITUDE_ENTITY, CONF_SET_HA_TIMEZONE, DOMAIN

_LOGGER = logging.getLogger(__name__)


class LocalTimezoneConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Local Timezone."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate that entities exist
            lat_entity = user_input[CONF_LATITUDE_ENTITY]
            lon_entity = user_input[CONF_LONGITUDE_ENTITY]

            lat_state = self.hass.states.get(lat_entity)
            lon_state = self.hass.states.get(lon_entity)

            if lat_state is None:
                errors[CONF_LATITUDE_ENTITY] = "entity_not_found"
            elif not _is_numeric(lat_state.state):
                errors[CONF_LATITUDE_ENTITY] = "invalid_value"

            if lon_state is None:
                errors[CONF_LONGITUDE_ENTITY] = "entity_not_found"
            elif not _is_numeric(lon_state.state):
                errors[CONF_LONGITUDE_ENTITY] = "invalid_value"

            if not errors:
                # Prevent duplicate entries
                await self.async_set_unique_id(
                    f"{lat_entity}_{lon_entity}"
                )
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="Local Timezone",
                    data=user_input,
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_LATITUDE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor"),
                ),
                vol.Required(CONF_LONGITUDE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor"),
                ),
                vol.Optional(CONF_SET_HA_TIMEZONE, default=True): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )


def _is_numeric(value: str) -> bool:
    """Check if a string is a valid number."""
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False
