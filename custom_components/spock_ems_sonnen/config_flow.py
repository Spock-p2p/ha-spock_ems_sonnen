"""Config flow para Spock EMS Sonnen."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigFlow, ConfigEntry, OptionsFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_API_TOKEN,
    CONF_PLANT_ID,
    CONF_SONNEN_IP,
    CONF_SONNEN_TOKEN,
    API_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)


async def validate_spock_auth(hass: HomeAssistant, api_token: str) -> dict[str, str]:
    """Valida el API token de Spock."""
    session = async_get_clientsession(hass)
    headers = {"X-Auth-Token": api_token}
    try:
        async with session.post(API_ENDPOINT, headers=headers, timeout=10) as resp:
            if resp.status == 403:
                return {"base": "invalid_auth"}
            return {}
    except Exception:
        _LOGGER.exception("No se pudo conectar a Spock al validar API token")
        return {"base": "cannot_connect"}


async def validate_sonnen(
    hass: HomeAssistant, sonnen_ip: str, sonnen_token: str
) -> dict[str, str]:
    """Valida la conexión a la batería Sonnen (IP + Auth-Token)."""
    session = async_get_clientsession(hass)
    # Intentar leer /api/v2/status (sin token) para verificar conectividad
    try:
        async with session.get(
            f"http://{sonnen_ip}/api/v2/status", timeout=10
        ) as resp:
            if resp.status != 200:
                return {"base": "cannot_connect_sonnen"}
    except Exception:
        _LOGGER.exception("No se pudo conectar a la batería Sonnen en %s", sonnen_ip)
        return {"base": "cannot_connect_sonnen"}

    # Verificar token con /api/v2/latestdata (requiere Auth-Token)
    try:
        headers = {"Auth-Token": sonnen_token}
        async with session.get(
            f"http://{sonnen_ip}/api/v2/latestdata", headers=headers, timeout=10
        ) as resp:
            if resp.status in (401, 403):
                return {"base": "invalid_sonnen_token"}
            if resp.status != 200:
                return {"base": "cannot_connect_sonnen"}
    except Exception:
        _LOGGER.exception("Error validando Auth-Token de Sonnen")
        return {"base": "cannot_connect_sonnen"}

    return {}


class SpockEmsSonnenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Maneja el flujo de configuración."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Paso inicial de configuración."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Validar Spock API token
            errors = await validate_spock_auth(self.hass, user_input[CONF_API_TOKEN])

            # Validar conexión Sonnen
            if not errors:
                errors = await validate_sonnen(
                    self.hass,
                    user_input[CONF_SONNEN_IP],
                    user_input[CONF_SONNEN_TOKEN],
                )

            if not errors:
                await self.async_set_unique_id(str(user_input[CONF_PLANT_ID]))
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Spock EMS Sonnen (Planta {user_input[CONF_PLANT_ID]})",
                    data=user_input,
                )

        STEP_USER_DATA_SCHEMA = vol.Schema(
            {
                vol.Required(CONF_API_TOKEN): str,
                vol.Required(CONF_PLANT_ID): int,
                vol.Required(CONF_SONNEN_IP): str,
                vol.Required(CONF_SONNEN_TOKEN): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlowHandler:
        """Obtiene el flujo de opciones para esta entrada."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(OptionsFlow):
    """Maneja el flujo de opciones (reconfiguración)."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Maneja el paso inicial del flujo de opciones."""
        errors: dict[str, str] = {}

        if user_input is not None:
            old_token = self.config_entry.options.get(
                CONF_API_TOKEN, self.config_entry.data[CONF_API_TOKEN]
            )
            if user_input[CONF_API_TOKEN] != old_token:
                errors = await validate_spock_auth(self.hass, user_input[CONF_API_TOKEN])

            old_sonnen_ip = self.config_entry.options.get(
                CONF_SONNEN_IP, self.config_entry.data[CONF_SONNEN_IP]
            )
            old_sonnen_token = self.config_entry.options.get(
                CONF_SONNEN_TOKEN, self.config_entry.data[CONF_SONNEN_TOKEN]
            )
            sonnen_changed = (
                user_input[CONF_SONNEN_IP] != old_sonnen_ip
                or user_input[CONF_SONNEN_TOKEN] != old_sonnen_token
            )
            if not errors and sonnen_changed:
                errors = await validate_sonnen(
                    self.hass,
                    user_input[CONF_SONNEN_IP],
                    user_input[CONF_SONNEN_TOKEN],
                )

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_API_TOKEN,
                    default=self.config_entry.options.get(
                        CONF_API_TOKEN, self.config_entry.data[CONF_API_TOKEN]
                    ),
                ): str,
                vol.Required(
                    CONF_PLANT_ID,
                    default=self.config_entry.options.get(
                        CONF_PLANT_ID, self.config_entry.data[CONF_PLANT_ID]
                    ),
                ): int,
                vol.Required(
                    CONF_SONNEN_IP,
                    default=self.config_entry.options.get(
                        CONF_SONNEN_IP, self.config_entry.data[CONF_SONNEN_IP]
                    ),
                ): str,
                vol.Required(
                    CONF_SONNEN_TOKEN,
                    default=self.config_entry.options.get(
                        CONF_SONNEN_TOKEN, self.config_entry.data[CONF_SONNEN_TOKEN]
                    ),
                ): str,
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=options_schema, errors=errors
        )
