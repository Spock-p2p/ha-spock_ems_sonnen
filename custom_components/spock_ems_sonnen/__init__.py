"""Integración Spock EMS Sonnen.

Lee telemetría de una batería sonnenBatterie vía su API REST local (v2),
la envía a Spock y aplica las órdenes recibidas (carga / descarga / auto).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_PLANT_ID,
    CONF_SONNEN_IP,
    CONF_SONNEN_TOKEN,
    DEFAULT_SCAN_INTERVAL_S,
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configura la integración desde la entrada de configuración."""
    coordinator = SpockEnergyCoordinator(hass, entry)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "is_enabled": True,
    }

    await asyncio.sleep(2)
    await coordinator.async_config_entry_first_refresh()
    _LOGGER.info("Spock EMS Sonnen: Primer fetch realizado.")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.info(
        "Spock EMS Sonnen: Ciclo automático iniciado cada %s.",
        coordinator.update_interval,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Descarga la entrada de configuración."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Recarga la entrada de configuración al modificar opciones."""
    await hass.config_entries.async_reload(entry.entry_id)


class SpockEnergyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator que gestiona el ciclo: Sonnen → Spock → Sonnen."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.config_entry = entry
        self.config = {**entry.data, **entry.options}

        self.api_token: str = self.config[CONF_API_TOKEN]
        self.plant_id: int = self.config[CONF_PLANT_ID]
        self.sonnen_ip: str = self.config[CONF_SONNEN_IP]
        self.sonnen_token: str = self.config[CONF_SONNEN_TOKEN]

        self._session = async_get_clientsession(hass)
        self._sonnen_base = f"http://{self.sonnen_ip}/api/v2"

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_S),
        )

        self._last_cmd_fingerprint: str | None = None

    # ---- Helpers ----

    @staticmethod
    def _str_or_none(value) -> str | None:
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _bool_str_or_none(value) -> str | None:
        if value is None:
            return None
        return str(bool(value)).lower()

    # ---- Lectura de la batería Sonnen (API REST local v2) ----

    async def _sonnen_get(self, path: str, auth: bool = False) -> dict:
        """GET genérico contra la API v2 de Sonnen."""
        url = f"{self._sonnen_base}{path}"
        headers = {"Auth-Token": self.sonnen_token} if auth else {}
        try:
            async with self._session.get(url, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    txt = await resp.text()
                    raise ValueError(f"Sonnen GET {path} → HTTP {resp.status}: {txt}")
                return await resp.json(content_type=None)
        except asyncio.TimeoutError:
            raise ValueError(f"Timeout al consultar Sonnen {path}")

    async def _read_sonnen_status(self) -> dict:
        """Lee /api/v2/status con Auth-Token."""
        return await self._sonnen_get("/status", auth=True)

    # ---- Escritura de órdenes a Sonnen ----

    async def _sonnen_post(self, path: str) -> None:
        """POST genérico (con Auth-Token) a Sonnen."""
        url = f"{self._sonnen_base}{path}"
        headers = {"Auth-Token": self.sonnen_token}
        async with self._session.post(url, headers=headers, timeout=10) as resp:
            if resp.status not in (200, 201):
                txt = await resp.text()
                _LOGGER.warning("Sonnen POST %s → HTTP %s: %s", path, resp.status, txt)

    async def _sonnen_put_config(self, payload: dict) -> None:
        """PUT /api/v2/configurations con Auth-Token."""
        url = f"{self._sonnen_base}/configurations"
        headers = {"Auth-Token": self.sonnen_token}
        async with self._session.put(url, headers=headers, json=payload, timeout=10) as resp:
            if resp.status not in (200, 201):
                txt = await resp.text()
                _LOGGER.warning("Sonnen PUT configurations → HTTP %s: %s", resp.status, txt)

    async def _set_operating_mode(self, mode: str) -> None:
        """Cambia el modo de operación: '1'=Manual, '2'=Auto/Self-Consumption."""
        _LOGGER.debug("Sonnen: Estableciendo EM_OperatingMode=%s", mode)
        await self._sonnen_put_config({"EM_OperatingMode": mode})

    async def _set_charge(self, watts: int) -> None:
        """Fuerza carga a X vatios."""
        _LOGGER.debug("Sonnen: Forzando carga a %d W", watts)
        await self._sonnen_post(f"/setpoint/charge/{watts}")

    async def _set_discharge(self, watts: int) -> None:
        """Fuerza descarga a X vatios."""
        _LOGGER.debug("Sonnen: Forzando descarga a %d W", watts)
        await self._sonnen_post(f"/setpoint/discharge/{watts}")

    # ---- Aplicar orden de Spock ----

    async def _apply_spock_command(self, spock: dict[str, Any]) -> None:
        """
        Aplica la orden recibida desde Spock sobre la batería Sonnen:
        - operation_mode: 'none' | 'charge' | 'discharge' | 'auto'
        - action: magnitud en W (siempre positiva en la API Spock) [solo charge/discharge]
        """
        op_mode = (spock.get("operation_mode") or "none").lower()

        # --- Modo NONE: no hacer nada ---
        if op_mode == "none":
            _LOGGER.debug("Spock: operation_mode=none. No se envía orden a Sonnen.")
            self._last_cmd_fingerprint = None
            return

        # --- Modo AUTO: volver a Self-Consumption (EM_OperatingMode=2) ---
        if op_mode == "auto":
            _LOGGER.debug("Spock: operation_mode=auto. Activando modo Self-Consumption en Sonnen.")
            try:
                await self._set_operating_mode("2")
                # Limpiar setpoints residuales
                await self._set_charge(0)
                await self._set_discharge(0)
                self._last_cmd_fingerprint = "auto"
            except Exception as e:
                _LOGGER.error("Fallo estableciendo modo Auto en Sonnen: %s", e)
            return

        # --- Charge / Discharge ---
        raw_action = spock.get("action", 0)
        try:
            mag = abs(int(float(raw_action)))
        except Exception:
            mag = 0

        if op_mode == "charge":
            _LOGGER.debug(
                "Spock: operation_mode=charge, %d W. Forzando carga en Sonnen.", mag
            )
            try:
                await self._set_operating_mode("1")
                await self._set_charge(mag)
                self._last_cmd_fingerprint = f"charge_{mag}"
            except Exception as e:
                _LOGGER.error("Fallo forzando carga en Sonnen: %s", e)

        elif op_mode == "discharge":
            _LOGGER.debug(
                "Spock: operation_mode=discharge, %d W. Forzando descarga en Sonnen.", mag
            )
            try:
                await self._set_operating_mode("1")
                await self._set_discharge(mag)
                self._last_cmd_fingerprint = f"discharge_{mag}"
            except Exception as e:
                _LOGGER.error("Fallo forzando descarga en Sonnen: %s", e)

        else:
            _LOGGER.warning("Spock: operation_mode desconocido: %r. Ignorando.", op_mode)

    # ---- Ciclo principal ----

    async def _async_update_data(self) -> dict[str, Any]:
        """
        Ciclo de 60 s:
        1) Lee telemetría de Sonnen (/api/v2/status)
        2) Envía telemetría a Spock (POST)
        3) Recibe orden de Spock y la aplica en Sonnen
        4) Devuelve telemetría + respuesta de Spock para los sensores
        """
        entry_id = self.config_entry.entry_id
        is_enabled = self.hass.data[DOMAIN].get(entry_id, {}).get("is_enabled", True)
        if not is_enabled:
            _LOGGER.debug("Sondeo API deshabilitado. Omitiendo ciclo.")
            return self.data

        _LOGGER.debug("Iniciando ciclo de actualización Spock EMS Sonnen")

        telemetry_data: dict[str, Any] = {}

        # ─── 1) Leer telemetría de Sonnen ───
        status: dict[str, Any] | None = None
        try:
            status = await self._read_sonnen_status()
            _LOGGER.debug("Sonnen /status (raw): %s", status)
        except Exception as e:
            _LOGGER.warning("No se pudo leer /api/v2/status de Sonnen: %r", e)

        # ─── 2) Mapeo normalizado ───
        if status is None:
            _LOGGER.warning("Sin telemetría de Sonnen. Enviando nulls a Spock.")
            telemetry_data = {
                "plant_id": str(self.plant_id),
                "bat_soc": None,
                "bat_power": None,
                "pv_power": None,
                "ongrid_power": None,
                "bat_charge_allowed": None,
                "bat_discharge_allowed": None,
                "bat_capacity": None,
                "total_grid_output_energy": None,
            }
        else:
            # SOC  (USOC = User SOC, el que ve el usuario)
            usoc = status.get("USOC")
            rsoc = status.get("RSOC")
            bat_soc = usoc if usoc is not None else rsoc

            # Potencia batería (Pac_total_W):
            #   negativo = cargando, positivo = descargando  (misma convención Spock)
            bat_power = status.get("Pac_total_W")

            # Potencia PV
            pv_power = status.get("Production_W")

            # Potencia red (GridFeedIn_W):
            #   Sonnen: positivo = exportando a red, negativo = importando de red
            #   Spock:  positivo = importando de red, negativo = exportando a red
            #   => invertir signo
            grid_feed = status.get("GridFeedIn_W")
            ongrid_power = -grid_feed if grid_feed is not None else None

            # Flags de carga/descarga
            bat_charge_allowed = bat_soc < 100 if bat_soc is not None else None
            bat_discharge_allowed = bat_soc > 0 if bat_soc is not None else None

            # Capacidad total (Wh) calculada desde RemainingCapacity_Wh / (RSOC/100)
            remaining_wh = status.get("RemainingCapacity_Wh")
            bat_capacity: int | None = None
            if remaining_wh is not None and rsoc is not None and rsoc > 0:
                try:
                    bat_capacity = int(round(float(remaining_wh) / (float(rsoc) / 100.0)))
                except Exception:
                    bat_capacity = None

            telemetry_data = {
                "plant_id": str(self.plant_id),
                "bat_soc": self._str_or_none(bat_soc),
                "bat_power": self._str_or_none(bat_power),
                "pv_power": self._str_or_none(pv_power),
                "ongrid_power": self._str_or_none(ongrid_power),
                "bat_charge_allowed": self._bool_str_or_none(bat_charge_allowed),
                "bat_discharge_allowed": self._bool_str_or_none(bat_discharge_allowed),
                "bat_capacity": self._str_or_none(bat_capacity),
                "total_grid_output_energy": None,
            }

            _LOGGER.debug("Telemetría normalizada: %s", telemetry_data)

        # ─── 3) POST a Spock (telemetría → comandos) ───
        _LOGGER.debug("Enviando telemetría a Spock API: %s", telemetry_data)
        headers = {"X-Auth-Token": self.api_token}

        try:
            async with self._session.post(
                API_ENDPOINT,
                headers=headers,
                json=telemetry_data,
            ) as resp:

                if resp.status == 403:
                    raise UpdateFailed("API Token inválido (403)")
                if resp.status != 200:
                    txt = await resp.text()
                    _LOGGER.error("API Spock error %s: %s", resp.status, txt)
                    raise UpdateFailed(f"Error de API Spock (HTTP {resp.status})")

                data = await resp.json(content_type=None)

                if not isinstance(data, dict) or "status" not in data or "operation_mode" not in data:
                    _LOGGER.warning("Formato de respuesta inesperado de Spock: %s", data)
                    raise UpdateFailed(f"Formato de respuesta inesperado: {data}")

                _LOGGER.debug("Comandos recibidos de Spock: %s", data)

                # ─── 4) Aplicar orden de Spock en Sonnen ───
                try:
                    await self._apply_spock_command(data)
                except Exception as cmd_err:
                    _LOGGER.error("Error aplicando orden de Spock en Sonnen: %s", cmd_err)

                return {
                    "telemetry": telemetry_data,
                    "spock": data,
                }

        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.error("Error en ciclo Spock EMS Sonnen (API POST): %s", err)
            raise UpdateFailed(f"Error en el ciclo de actualización: {err}") from err
