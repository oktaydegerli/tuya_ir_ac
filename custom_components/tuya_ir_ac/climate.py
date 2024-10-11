import asyncio
import time
import logging
from contextlib import contextmanager
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.restore_state import RestoreEntity
from typing import Any, Callable, Dict, Optional
from .ac_state import ACState
from .client import AC

from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_PASSWORD,
    CONF_USERNAME,
    TEMP_CELSIUS,
)
from homeassistant.components.climate import (
    ClimateEntity,
    PLATFORM_SCHEMA,
)

from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
    HomeAssistantType,
)

from homeassistant.components.climate.const import (
    CURRENT_HVAC_OFF,
    CURRENT_HVAC_IDLE,
    CURRENT_HVAC_COOL,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_DRY,
    HVAC_MODE_OFF,
    HVAC_MODE_COOL,
    HVAC_MODE_FAN_ONLY,
    HVAC_MODE_DRY,
    HVAC_MODE_HEAT,
    HVAC_MODE_HEAT_COOL,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_FAN_MODE
)

_LOGGER = logging.getLogger(__name__)

# CONF_AC_ID = "id"
CONF_ACS = "acs"
CONF_AC_NAME = "name"
CONF_AC_TUYA_IR_DEVICE_ID = "tuya_ir_device_id"
CONF_AC_TUYA_DEVICE_LOCAL_KEY = "tuya_device_local_key"
CONF_AC_TUYA_DEVICE_IP = "tuya_device_ip"
CONF_AC_TUYA_DEVICE_VERSION = "tuya_device_version"

DEFAULT_NAME = "TuyaIRAC"
print("")


AC_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_AC_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_AC_TUYA_IR_DEVICE_ID): cv.string,
        vol.Required(CONF_AC_TUYA_DEVICE_LOCAL_KEY): cv.string,
        vol.Required(CONF_AC_TUYA_DEVICE_IP): cv.string,
        vol.Required(CONF_AC_TUYA_DEVICE_VERSION, default='3.3'): cv.string,
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ACS): vol.All(cv.ensure_list, [AC_SCHEMA]),
    }
)

FAN_MODES = ['Auto', 'Low', 'Medium-Low', 'Medium', 'Medium-High', 'High', 'Turbo', 'Quiet']

async def async_setup_platform(
        hass: HomeAssistantType,
        config: ConfigType,
        async_add_entities: Callable,
        discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    # Note: since this is a global thing, if at least one entity activates it, it's on
    """Set up the TuyaIRAC platform."""
    _LOGGER.debug("Setting up the TuyaIRAC climate platform conf: %s", config)
    session = async_get_clientsession(hass)

    fan_modes = FAN_MODES

    acs = [
        TuyaIRAC(hass, ac, fan_modes)
        for ac in config.get(CONF_ACS)
    ]

    async_add_entities(acs, update_before_add=True)


class TuyaIRAC(RestoreEntity, ClimateEntity):
    def __init__(self, hass, ac_conf, fan_modes):
        """Initialize the thermostat."""
        _LOGGER.info("Initializing TuyaIRAC", ac_conf)
        self._name = ac_conf[CONF_AC_NAME]
        self._hass = hass
        self._state = ACState(self, self._hass)
        self._fan_mode = None
        self._fan_modes = fan_modes
        self.ac = AC(
            ac_conf[CONF_AC_TUYA_IR_DEVICE_ID],
            ac_conf[CONF_AC_TUYA_DEVICE_LOCAL_KEY],
            ac_conf[CONF_AC_TUYA_DEVICE_IP],
            ac_conf[CONF_AC_TUYA_DEVICE_VERSION],
            self._state
        )


    async def async_added_to_hass(self):
        """Set up the thermostat."""
        await super().async_added_to_hass()

        _LOGGER.info("Setting up TuyaIRAC")
        await self._hass.async_add_executor_job(self.ac.setup)
        prev = await self.async_get_last_state()
        _LOGGER.info("prev data %s", prev)
        if prev:
            _LOGGER.info("prev state: %s", prev.state)
            _LOGGER.info("prev attributes: %s", prev.attributes)
            self._state.set_initial_state(prev.attributes.get("internal_mode", None), prev.attributes.get("internal_temp", None), prev.attributes.get("internal_fan_speed", None))

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {
            "internal_mode": self._state.mode,
            "internal_fan_speed": self._state.fan_speed,
            "internal_temp": self._state.temp,
        }

    # managed properties

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self) -> str:
        """Return the unique ID for this thermostat."""
        return f"climate {self._name}"

    @property
    def should_poll(self):
        """Return if polling is required."""
        return False

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return 16

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return 31

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def current_temperature(self):
        """Return the current temperature."""
        value = self._state.temp
        if value is not None:
            value = int(value)
        _LOGGER.debug(f"value of current_temperature property: {value}")
        return value

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""

        if self._state.mode == 'off':
            _LOGGER.debug(f"target_temperature: ac is off")
            return None

        value = self._state.temp
        if value is not None:
            value = int(value)
        _LOGGER.debug(f"value of target_temperature property: {value}")
        return value

    @property
    def target_temperature_step(self):
        return 1

    MODE_BY_NAME = {"IDLE": CURRENT_HVAC_IDLE}

    HVAC_MODE_MAPPING = {
        "OFF": HVAC_MODE_OFF,
        "COOL": HVAC_MODE_COOL,
        "FAN": HVAC_MODE_FAN_ONLY,
        "DRY": HVAC_MODE_DRY,
        "HEAT": HVAC_MODE_HEAT,
        "AUTO": HVAC_MODE_HEAT_COOL,
    }

    HVAC_MODE_MAPPING_INV = {v: k for k, v in HVAC_MODE_MAPPING.items()}

    @property
    def hvac_mode(self):
        """Return hvac operation ie. heat, cool mode."""
        
        if self._state.mode == 'off':
            _LOGGER.debug(f"hvac_mode: ac is off")
            return HVAC_MODE_OFF

        if self._state.mode == 'cool':
            _LOGGER.debug(f"hvac_mode: ac is cool")
            return HVAC_MODE_COOL

        if self._state.mode == 'heat':
            _LOGGER.debug(f"hvac_mode: ac is heat")
            return HVAC_MODE_HEAT

        if self._state.mode == 'auto':
            _LOGGER.debug(f"hvac_mode: ac is auto")
            return HVAC_MODE_HEAT_COOL

        if self._state.mode == 'fan':
            _LOGGER.debug(f"hvac_mode: ac is fan")
            return HVAC_MODE_FAN_ONLY

        if self._state.mode == 'dry':
            _LOGGER.debug(f"hvac_mode: ac is dry")
            return HVAC_MODE_DRY

        else:
            _LOGGER.warning(f"hvac_mode: unknown mode: " + self._state.mode)

            # Not returning off as if it's on then we would be completely off
            return HVAC_MODE_OFF

    @property
    def hvac_modes(self):
        """HVAC modes."""
        return [
            HVAC_MODE_OFF,
            HVAC_MODE_COOL,
            HVAC_MODE_FAN_ONLY,
            HVAC_MODE_DRY,
            HVAC_MODE_HEAT,
            HVAC_MODE_HEAT_COOL,
        ]

    @property
    def fan_mode(self):
        return self._fan_mode

    @property
    def fan_modes(self):
        return self._fan_modes

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_TARGET_TEMPERATURE | SUPPORT_FAN_MODE

    # actions

    def set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        _LOGGER.debug(f"setting new temperature to {temperature}")
        if temperature is None:
            return

        temperature = int(temperature)
        with self._act_and_update():
            self.ac.update_temp(temperature)

        _LOGGER.debug(f"new temperature was set to {temperature}")

    def set_hvac_mode(self, hvac_mode):
        _LOGGER.debug(f"setting hvac mode to {hvac_mode}")

        ac_mode = None

        if hvac_mode == HVAC_MODE_OFF:
            _LOGGER.debug(f"set_hvac_mode: ac is cool")
            ac_mode = 'off'

        if hvac_mode == HVAC_MODE_COOL:
            _LOGGER.debug(f"set_hvac_mode: ac is cool")
            ac_mode = 'cool'

        if hvac_mode == HVAC_MODE_HEAT:
            _LOGGER.debug(f"set_hvac_mode: ac is heat")
            ac_mode = 'heat'

        if hvac_mode == HVAC_MODE_HEAT_COOL:
            _LOGGER.debug(f"set_hvac_mode: ac is auto")
            ac_mode = 'auto'

        if hvac_mode == HVAC_MODE_FAN_ONLY:
            _LOGGER.debug(f"set_hvac_mode: ac is fan")
            ac_mode = 'fan'

        if hvac_mode == HVAC_MODE_DRY:
            _LOGGER.debug(f"set_hvac_mode: ac is dry")
            ac_mode = 'dry'

        if ac_mode is None:
            _LOGGER.warning("Unsupported mode " + hvac_mode)
            return

        _LOGGER.debug(f"setting hvac mode to {hvac_mode} (ac_mode {ac_mode})")
        with self._act_and_update():
            self.ac.update_mode(ac_mode)

        _LOGGER.debug(f"hvac mode was set to {hvac_mode} (ac_mode {ac_mode})")

    def set_fan_mode(self, fan_mode):
        _LOGGER.debug(f"set_fan_mode: setting fan mode to {fan_mode}")

        fan_speed = None

        if fan_mode == 'Auto':
            fan_speed = 'low'

        if fan_mode == 'Low':
            fan_speed = 'medium'

        if fan_mode == 'Medium-Low':
            fan_speed = 'high'

        if fan_mode == 'Medium':
            fan_speed = 'auto'

        if fan_mode == 'Medium-High':
            fan_speed = 'auto'

        if fan_mode == 'High':
            fan_speed = 'auto'

        if fan_mode == 'Turbo':
            fan_speed = 'auto'

        if fan_mode == 'Quiet':
            fan_speed = 'auto'                      

        if fan_speed is None:
            _LOGGER.warning("Unsupported fan_mode: " + fan_mode)
            return

        _LOGGER.debug(f"setting fan mode to {fan_mode} (fan_speed {fan_speed})")
        with self._act_and_update():
            self.ac.update_fan_speed(fan_speed)
        _LOGGER.debug(f"fan mode was set to {fan_mode} (fan_speed {fan_speed})")

    @contextmanager
    def _act_and_update(self):
        yield

        asyncio.run_coroutine_threadsafe(
            self.async_update_ha_state(), self._hass.loop
        )

    # data fetch mechanism
    def update(self):
        """Get the latest data."""
        _LOGGER.debug("not doing anything, should I even use it?")