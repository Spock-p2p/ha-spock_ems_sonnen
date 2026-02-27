# Spock EMS (sonnenBatterie) - Integracion para Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)

Custom component de Home Assistant que integra baterias **sonnenBatterie** con la plataforma **Spock P2P** de gestion energetica.

**Para utilizar esta integracion es imprescindible crear una cuenta en Spock: https://spock.es/register**

## Que hace este modulo

El modulo realiza un ciclo automatico cada **60 segundos**:

1. **Lee telemetria** de la bateria Sonnen via su API REST local (`/api/v2/status`).
2. **Envia la telemetria** al servidor de Spock (`POST https://ems-ha.spock.es/api/ems_sonnen`).
3. **Recibe una orden** de Spock (carga, descarga, auto o ninguna).
4. **Aplica la orden** sobre la bateria Sonnen via su API REST local (setpoints de carga/descarga, cambio de modo operativo).

```
sonnenBatterie                Spock Cloud
  (LAN)                       (HTTPS)
    |                            |
    |  GET /api/v2/status        |
    |<---------------------------|
    |   telemetria (JSON)        |
    |--------------------------->|
    |                            |  POST /api/ems_sonnen
    |                            |  (telemetria)
    |                            |
    |                            |  Respuesta: orden
    |                            |  {operation_mode, action}
    |  POST setpoint/charge/W    |
    |  PUT  configurations       |
    |<---------------------------|
    |                            |
```

---

## Requisitos previos

- **Home Assistant** >= 2024.6.0
- Una **sonnenBatterie** accesible en tu red local (IP fija recomendada).
- La **Write API** habilitada en la sonnenBatterie (necesario para enviar ordenes de carga/descarga).
- El **Auth Token** de la bateria (se obtiene desde el dashboard web de la sonnenBatterie, en _Software-Integration > Web API > Token_).
- Una cuenta en **Spock** con `api_token` y `plant_id` asignados.

### Habilitar la Write API en Sonnen

Para que el modulo pueda enviar ordenes de carga/descarga a la bateria:

1. Accede al dashboard web de tu sonnenBatterie: `http://IP_DE_TU_SONNEN`
2. Ve a **Software-Integration** (o similar segun firmware).
3. Habilita la **Write API**.
4. Copia el **Auth Token** que aparece.
5. Si la bateria esta vinculada al VPP (Virtual Power Plant) de Sonnen, puede que necesites desconectarla y poner el modo en **Manual** para que acepte ordenes externas.

---

## Instalacion

### Via HACS (recomendado)

1. Asegurate de tener [HACS](https://hacs.xyz/) instalado en tu Home Assistant.
2. Ve a la seccion de HACS en tu panel de Home Assistant.
3. Haz clic en "Integraciones".
4. Haz clic en el menu de tres puntos en la esquina superior derecha y selecciona "Repositorios personalizados".
5. En el campo "Repositorio", pega la URL: `https://github.com/Spock-p2p/ha-spock_ems_sonnen`
6. En la categoria, selecciona "Integracion".
7. Haz clic en "Anadir".
8. Busca "Spock EMS (Sonnen)" e instala.
9. Reinicia Home Assistant.

### Instalacion Manual

1. Descarga la ultima version desde [releases](https://github.com/Spock-p2p/ha-spock_ems_sonnen/releases).
2. Copia la carpeta `custom_components/spock_ems_sonnen/` en el directorio `config/custom_components/` de tu Home Assistant.
   - La ruta final debe ser: `<config_dir>/custom_components/spock_ems_sonnen/`
3. Reinicia Home Assistant.

---

## Configuracion

Tras instalar, ve a **Ajustes > Dispositivos y servicios > Agregar integracion** y busca **Spock EMS (Sonnen)**.

### Parametros de configuracion

| Parametro | Descripcion |
|---|---|
| **Spock EMS API Token** | Token de autenticacion de tu cuenta en Spock (cabecera `X-Auth-Token`). |
| **Spock EMS Plant ID** | Identificador numerico unico de tu planta en Spock. |
| **sonnenBatterie IP** | Direccion IP local de tu bateria (ej: `192.168.1.50`). |
| **sonnenBatterie Auth Token** | Token de la API local de la bateria (cabecera `Auth-Token`). Se obtiene del dashboard web de la Sonnen. |

### Validaciones durante la configuracion

El flujo de configuracion verifica automaticamente:

1. Que el **API Token de Spock** sea valido (consulta la API de Spock).
2. Que la **IP de la sonnenBatterie** sea alcanzable (consulta `GET /api/v2/status`).
3. Que el **Auth Token de la bateria** sea correcto (consulta `GET /api/v2/latestdata` con el token).

Todos los parametros se pueden modificar despues desde las **Opciones** de la integracion (sin necesidad de borrar y recrear).

---

## Entidades creadas

### Sensores de telemetria (desde la bateria)

| Entidad | Descripcion | Unidad | Tipo |
|---|---|---|---|
| **Bateria SOC** | Estado de carga de la bateria (USOC). | % | Medicion |
| **Bateria Potencia** | Potencia de la bateria. Negativo = cargando, Positivo = descargando. | W | Medicion |
| **PV Potencia** | Produccion fotovoltaica actual. | W | Medicion |
| **Red Potencia (PCC)** | Potencia en el punto de conexion a red. Positivo = importando, Negativo = exportando. | W | Medicion |
| **Capacidad Bateria (Wh)** | Capacidad total estimada de la bateria. | - | - |
| **Bateria: Carga Permitida** | `true` si SOC < 100%. | - | Texto |
| **Bateria: Descarga Permitida** | `true` si SOC > 0%. | - | Texto |

### Sensores de Spock (desde la nube)

| Entidad | Descripcion |
|---|---|
| **Spock Modo** | Modo de operacion recibido de Spock (`none`, `auto`, `charge`, `discharge`). |
| **Spock Status** | Estado de la ultima respuesta de la API de Spock. |

### Switch

| Entidad | Descripcion |
|---|---|
| **Polling habilitado** | Activa/desactiva el ciclo de polling. Si se apaga, el modulo deja de leer telemetria y enviar ordenes. |

---

## Modos de operacion (ordenes de Spock)

Spock envia una orden en cada respuesta al POST de telemetria. El modulo la interpreta y la ejecuta sobre la sonnenBatterie:

| Modo Spock | Accion en Sonnen | Detalle tecnico |
|---|---|---|
| `none` | No hace nada | La bateria mantiene su estado actual. |
| `auto` | Modo Self-Consumption | `PUT /configurations` con `EM_OperatingMode = 2`. Limpia setpoints residuales. |
| `charge` | Carga forzada a X vatios | `PUT /configurations` con `EM_OperatingMode = 1` (Manual) + `POST /setpoint/charge/{W}`. |
| `discharge` | Descarga forzada a X vatios | `PUT /configurations` con `EM_OperatingMode = 1` (Manual) + `POST /setpoint/discharge/{W}`. |

---

## Detalle tecnico de las APIs utilizadas

### API local de Sonnen (REST v2)

**Base URL:** `http://{IP}/api/v2`

#### Lectura (cada 60s, sin token)

```bash
curl http://192.168.1.50/api/v2/status
```

Campos utilizados de la respuesta:

| Campo Sonnen | Campo Spock | Transformacion |
|---|---|---|
| `USOC` | `bat_soc` | Directo (%, 0-100) |
| `RSOC` | `bat_soc` (fallback) | Si USOC no esta disponible |
| `Pac_total_W` | `bat_power` | Directo (negativo=carga, positivo=descarga) |
| `Production_W` | `pv_power` | Directo (W) |
| `GridFeedIn_W` | `ongrid_power` | **Signo invertido** (Sonnen: +export/-import -> Spock: +import/-export) |
| `RemainingCapacity_Wh` + `RSOC` | `bat_capacity` | `RemainingCapacity_Wh / (RSOC / 100)` = capacidad total |

#### Escritura (bajo demanda, con Auth-Token)

```bash
# Cambiar modo operativo (1=Manual, 2=Auto/Self-Consumption)
curl -X PUT -H "Auth-Token: TU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"EM_OperatingMode": "1"}' \
  http://192.168.1.50/api/v2/configurations

# Forzar carga a 3300 W
curl -X POST -H "Auth-Token: TU_TOKEN" \
  http://192.168.1.50/api/v2/setpoint/charge/3300

# Forzar descarga a 3300 W
curl -X POST -H "Auth-Token: TU_TOKEN" \
  http://192.168.1.50/api/v2/setpoint/discharge/3300
```

### API de Spock (nube)

```bash
curl -X POST \
  -H "X-Auth-Token: TU_SPOCK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"plant_id":"123","bat_soc":"75","bat_power":"-1000","pv_power":"3500","ongrid_power":"500",...}' \
  https://ems-ha.spock.es/api/ems_sonnen
```

Respuesta tipica:

```json
{
  "status": "ok",
  "operation_mode": "charge",
  "action": 2000
}
```

---

## Convencion de signos

| Magnitud | Positivo | Negativo |
|---|---|---|
| `bat_power` | Descargando (bateria -> casa) | Cargando (red/PV -> bateria) |
| `ongrid_power` | Importando de red | Exportando a red |
| `pv_power` | Produciendo | - |

---

## Estructura del proyecto

```
custom_components/spock_ems_sonnen/
    __init__.py          # Coordinator principal (ciclo Sonnen -> Spock -> Sonnen)
    const.py             # Constantes y claves de configuracion
    config_flow.py       # Flujo de configuracion (setup + opciones)
    sensor.py            # Entidades sensor (telemetria + Spock)
    switch.py            # Switch de polling on/off
    manifest.json        # Metadatos de la integracion
    translations/
        en.json          # Cadenas en ingles
        es.json          # Cadenas en espanol
```

---

## Troubleshooting

### La bateria no responde

- Verifica que la IP de la sonnenBatterie es correcta y accesible desde la red de Home Assistant.
- Comprueba que `http://IP/api/v2/status` responde en un navegador.
- Si usas Docker/HAOS, asegurate de que la red del contenedor tiene acceso a la LAN.

### Error de Auth Token de Sonnen

- Verifica que el Auth Token es correcto. Se obtiene desde el dashboard web de la bateria en _Software-Integration > Web API > Token_.
- Comprueba que la **Write API** esta habilitada en la sonnenBatterie.
- Prueba manualmente: `curl -H "Auth-Token: TU_TOKEN" http://IP/api/v2/latestdata`

### Las ordenes de carga/descarga no se aplican

- Asegurate de que la **Write API** esta habilitada.
- Si la bateria esta en modo VPP, puede rechazar ordenes externas. Desvinculala del VPP.
- Verifica que el modo no esta bloqueado por el instalador.
- Prueba manualmente: `curl -X POST -H "Auth-Token: TU_TOKEN" http://IP/api/v2/setpoint/charge/500`

### Error de conexion a Spock

- Comprueba que tu Home Assistant tiene acceso a internet.
- Verifica que el API Token de Spock es correcto.
- Revisa que el `plant_id` es el correcto para tu instalacion.

### Logs de depuracion

Agrega esto a tu `configuration.yaml` para ver los logs detallados:

```yaml
logger:
  logs:
    custom_components.spock_ems_sonnen: debug
```

---

## Contribuciones

Las contribuciones son bienvenidas. Por favor, abre un [issue](https://github.com/Spock-p2p/ha-spock_ems_sonnen/issues) para reportar bugs o un pull request para proponer mejoras.

## Licencia

Apache 2.0 - Copyright 2026 Spock P2P SL
