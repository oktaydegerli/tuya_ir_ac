from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import HVACMode, ClimateEntityFeature
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.event import async_track_state_change
from .const import DOMAIN, CONF_AC_NAME, CONF_DEVICE_ID, CONF_DEVICE_LOCAL_KEY, CONF_DEVICE_IP, CONF_DEVICE_VERSION, CONF_DEVICE_MODEL, CONF_TEMPERATURE_SENSOR

import tinytuya
import os
import json
import codecs
import logging
import threading

_LOGGER = logging.getLogger(__name__)

ir_codes1 = None
ir_codes2 = None

current_dir = os.path.dirname(__file__)
commands_path1 = os.path.join(current_dir, 'MSZ-GE25VA.json')
commands_path2 = os.path.join(current_dir, 'MSC-GE35VB.json')

with open(commands_path1, 'r') as file:
    ir_codes1 = json.load(file)

with open(commands_path2, 'r') as file:
    ir_codes2 = json.load(file)


async def async_setup_entry(hass, config_entry, async_add_entities):
    ac_name = config_entry.data.get(CONF_AC_NAME)
    device_id = config_entry.data.get(CONF_DEVICE_ID)
    device_model = config_entry.data.get(CONF_DEVICE_MODEL)
    device_local_key = config_entry.data.get(CONF_DEVICE_LOCAL_KEY)
    device_ip = config_entry.data.get(CONF_DEVICE_IP)
    device_version = config_entry.data.get(CONF_DEVICE_VERSION)
    temperature_sensor = config_entry.data.get(CONF_TEMPERATURE_SENSOR)
    
    async_add_entities([TuyaIrClimateEntity(ac_name, device_id, device_local_key, device_ip, device_version, device_model, temperature_sensor)])

class TuyaIrClimateEntity(ClimateEntity, RestoreEntity):
    def __init__(self, ac_name, device_id, device_local_key, device_ip, device_version, device_model, temperature_sensor):
        self._enable_turn_on_off_backwards_compatibility = False
        self._ac_name = ac_name
        self._device_id = device_id
        self._device_local_key = device_local_key
        self._device_ip = device_ip
        self._device_version = device_version
        self._device_model = device_model
        self._temperature_sensor = temperature_sensor
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_fan_mode = "Orta"
        self._attr_target_temperature = 22
        self._attr_current_temperature = None
        self._lock = threading.Lock()
        self._device_api = None

    async def async_added_to_hass(self):

        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_hvac_mode = last_state.state
            self._attr_fan_mode = last_state.attributes.get('fan_mode')
            self._attr_target_temperature = last_state.attributes.get('temperature')

        if self._temperature_sensor:
            async_track_state_change(self.hass, self._temperature_sensor, self._async_sensor_changed)
            self.async_schedule_update_ha_state(force_refresh=True)

    async def _async_sensor_changed(self, entity_id, old_state, new_state):
        if new_state is None:
            return
        try:
                self._attr_current_temperature = float(new_state.state)
                self.async_write_ha_state()
        except (TypeError, ValueError) as e:
                _LOGGER.warning(f"Geçersiz sıcaklık sensörü değeri: {new_state.state} - Hata: {e}")

    @property
    def unique_id(self) -> str:
        return f"{self._device_id}_{self._ac_name}"

    @property
    def name(self):
        return self._ac_name

    @property
    def supported_features(self):
        return (ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE |
                ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF)

    @property
    def temperature_unit(self):
        return UnitOfTemperature.CELSIUS

    @property
    def min_temp(self):
        return 16

    @property
    def max_temp(self):
        return 31

    @property
    def target_temperature_step(self):
        return 1

    @property
    def hvac_modes(self):
        return [HVACMode.OFF, HVACMode.COOL, HVACMode.FAN_ONLY, HVACMode.DRY, HVACMode.HEAT, HVACMode.HEAT_COOL]

    @property
    def hvac_mode(self):
        return self._attr_hvac_mode

    @property
    def fan_modes(self):
        return ['Otomatik', 'Sessiz', 'Düşük', 'Orta', 'Yüksek', 'En Yüksek']
    
    @property
    def fan_mode(self):
        return self._attr_fan_mode
    
    @property
    def current_temperature(self):
        return 20

    @property
    def target_temperature(self):
        return self._attr_target_temperature
    
    async def async_set_hvac_mode(self, hvac_mode: HVACMode):
        if hvac_mode is not None:
            self._attr_hvac_mode = hvac_mode
            await self._set_state()

    async def async_set_fan_mode(self, fan_mode: str):
        if fan_mode is not None:
            self._attr_fan_mode = fan_mode
            if self._attr_hvac_mode == HVACMode.OFF or self._attr_hvac_mode is None:
                self._attr_hvac_mode = HVACMode.HEAT_COOL
            await self._set_state()
    
    async def async_set_temperature(self, **kwargs):
        target_temperature = kwargs.get('temperature')
        if target_temperature is not None:
            self._attr_target_temperature = int(target_temperature)
            if self._attr_hvac_mode == HVACMode.OFF or self._attr_hvac_mode is None:
                self._attr_hvac_mode = HVACMode.HEAT_COOL
            await self._set_state()

    async def async_turn_on(self):
        self._attr_hvac_mode = HVACMode.HEAT_COOL
        await self._set_state()

    async def async_turn_off(self):
        self._attr_hvac_mode = HVACMode.OFF
        await self._set_state()

    async def _set_state(self):

        self.async_write_ha_state()

        if self._attr_hvac_mode == HVACMode.OFF:
            hvac_mode_key = "off"
        elif self._attr_hvac_mode == HVACMode.HEAT_COOL:
            hvac_mode_key = "auto"
        elif self._attr_hvac_mode == HVACMode.COOL:
            hvac_mode_key = "cool"
        elif self._attr_hvac_mode == HVACMode.HEAT:
            hvac_mode_key = "heat"
        elif self._attr_hvac_mode == HVACMode.DRY:
            hvac_mode_key = "dry"
        elif self._attr_hvac_mode == HVACMode.FAN_ONLY:
            hvac_mode_key = "fan"
        else:
            msg = 'Mode must be one of off, cool, heat, dry, fan or auto'
            raise Exception(msg)

        if self._attr_fan_mode == 'Otomatik':
            fan_mode_key = 'auto'
        elif self._attr_fan_mode == 'Sessiz':
            fan_mode_key = 'quiet'
        elif self._attr_fan_mode == 'Düşük':
            fan_mode_key = 'low'
        elif self._attr_fan_mode == 'Orta':
            fan_mode_key = 'medium'
        elif self._attr_fan_mode == 'Yüksek':
            fan_mode_key = 'high'
        elif self._attr_fan_mode == 'En Yüksek':
            fan_mode_key = 'highest'                    
        else:
            msg = 'Fan mode must be one of Otomatik, Sessiz, Düşük, Orta, Yüksek or En Yüksek'
            raise Exception(msg)


        if hvac_mode_key == "off":
            if self._device_model == 'MSZ-GE25VA':
                ir_code = ir_codes1["off"]
            else:
                ir_code = ir_codes2["off"]
        else: 
            if self._device_model == 'MSZ-GE25VA':
                ir_code = ir_codes1[hvac_mode_key][fan_mode_key][str(self._attr_target_temperature)]
            else:
                ir_code = ir_codes2[hvac_mode_key][fan_mode_key][str(self._attr_target_temperature)]

        b64 = codecs.encode(codecs.decode(ir_code, 'hex'), 'base64').decode()

        command = {"1": "study_key", "7": b64}

        if self._lock.locked() and self._device_api is None:
            return
        
        with self._lock:
            await self.hass.async_add_executor_job(self._send_command, command)

    def _send_command(self, command):
        if self._device_api is None:
            self._device_api = tinytuya.Device(self._device_id, self._device_ip, self._device_local_key, "default", 5, self._device_version)
        payload = self._device_api.generate_payload(tinytuya.CONTROL, command)
        self._device_api.send(payload)