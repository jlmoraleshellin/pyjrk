import os
from typing import Callable, Protocol, runtime_checkable
import yaml
from ctypes import *
from pyjrk.pyjrk_protocol import jrk_constant as jc
from pyjrk.pyjrk_structures import *
from functools import wraps, partial
import logging
import platform

@runtime_checkable
class LoggerProtocol(Protocol):
    def info(self, message: str, *args, **kwargs) -> None: ...
    def debug(self, message: str, *args, **kwargs) -> None: ...
    def warning(self, message: str, *args, **kwargs) -> None: ...

# [J]rk [E]rror [D]ecoder
def JED(func):
    @wraps(func)
    def func_wrapper(*args, **kwargs):
        _e_p = func(*args, **kwargs)
        if bool(_e_p):
            _e = cast(_e_p, POINTER(jrk_error))
            _logger = logging.getLogger('PyJrk')
            _logger.error(_e.contents.message)
            return 1
        else:
            return 0
    return func_wrapper

class PyJrk(object):
    # Type annotations for dynamically created methods
    set_target: Callable[[int], int]
    stop_motor: Callable[[], int]
    force_duty_cycle_target: Callable[[], int]
    force_duty_cycle: Callable[[], int]
    reinitialize: Callable[[int], int]
    
    def __init__(self, logger: LoggerProtocol = None):
        self._logger = logger if logger else self._initialize_default_logger()
        self._load_drivers()
        
        self.device = None
        self.handle = None
        self.settings = None
        self.variables = None
        self._commands = [('set_target', c_uint16),
                          ('stop_motor', None),
                          ('force_duty_cycle_target', None),
                          ('force_duty_cycle', None),
                          ('reinitialize', c_uint8),]
        self._create_jrk_command_attributes()

    def _initialize_default_logger(self):
        # - Logging - 
        self._log_level = logging.DEBUG
        _logger = logging.getLogger('PyJrk')
        _logger.setLevel(self._log_level)
        _formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        # Console Logging
        _ch = logging.StreamHandler()
        _ch.setLevel(self._log_level)
        _ch.setFormatter(_formatter)
        _logger.addHandler(_ch)
        return _logger
    
    @property
    def log_level(self):
        return self._log_level

    @log_level.setter
    def log_level(self, level):
        self._log_level = level
        self._logger.setLevel(level)

    def _load_drivers(self):
        # Driver Locations (x64)
        file_path = os.path.dirname(os.path.abspath(__file__))
        if platform.system() == 'Windows':
            # Windows DLL paths
            self.usblib = windll.LoadLibrary(file_path + "\\drivers\\x64\\libusbp-1.dll") # type: ignore
            self.jrklib = windll.LoadLibrary(file_path + "\\drivers\\x64\\libpololu-jrk2-1.dll") # type: ignore
        elif platform.system() == 'Linux':
            # Linux shared library paths
            self.usblib = CDLL(file_path + "/drivers/linux/libusbp-1.so")
            self.jrklib = CDLL(file_path + "/drivers/linux/libpololu-jrk2-1.so")
        self._logger.debug("JRK Drivers loaded")

    def _create_jrk_command_attributes(self):
        for cmd_name, value_c_type in self._commands:
            if bool(value_c_type):
                setattr(self.__class__, cmd_name, partial(self._jrk_command_with_value, cmd_name, value_c_type))
            else:
                setattr(self.__class__, cmd_name, partial(self._jrk_command, cmd_name))

    @JED
    def _jrk_command(self, cmd_name):
        e_p = getattr(self.jrklib,'jrk_'+ cmd_name)(byref(self.handle))
        return e_p

    @JED
    def _jrk_command_with_value(self, cmd_name, value_c_type, value):
        if 'JRK' in str(value):
            value = jc[value]
        e_p = getattr(self.jrklib,'jrk_'+ cmd_name)(byref(self.handle), value_c_type(value))
        return e_p

    @JED
    def _list_connected_devices(self):
        self._devcnt = c_size_t(0)
        self._dev_pp = POINTER(POINTER(jrk_device))()
        e_p = self.jrklib.jrk_list_connected_devices(byref(self._dev_pp), byref(self._devcnt))
        return e_p

    @JED
    def _jrk_handle_open(self):
        handle_p = POINTER(jrk_handle)()
        e_p = self.jrklib.jrk_handle_open(byref(self.device), byref(handle_p))
        self.handle = handle_p[0]
        return e_p

    def list_connected_device_serial_numbers(self):
        self._list_connected_devices()
        jrk_list = []
        if not self._devcnt.value:
            self._logger.warning("No Jrk devices connected.")
        for i in range(0, self._devcnt.value):
            jrkdev = self._dev_pp[0][i]
            jrk_list.append(jrkdev.serial_number.decode('utf-8'))
        return jrk_list

    def connect_to_serial_number(self, serial_number):
        self._list_connected_devices()
        for i in range(0, self._devcnt.value):
            if serial_number == self._dev_pp[0][i].serial_number.decode('utf-8'):
                self.device = self._dev_pp[0][i]
                self._jrk_handle_open()
                self.variables = PyJrk_Variables(self.handle, (self.usblib, self.jrklib), self._logger)
                # TEST there is no product field in PyJrk_variables
                # Maybe retrieve product from the jrk_device object, otherwise provide through config
                self.settings = PyJrk_Settings(self.handle, (self.usblib, self.jrklib), int(self.device.product), self._logger)
                return 0
        if not self.device:
            self._logger.error("Serial number device not found.")
            return 1


class PyJrk_Variables(object):
    def __init__(self, device_handle, driver_handles, logger: LoggerProtocol):
        self._device_handle = device_handle
        self.usblib, self.jrklib = driver_handles
        self._logger = logger

        self._jrk_variables_p = POINTER(jrk_variables)()
        self._jrk_variables = jrk_variables()
        
        self.pin_info = []
        for i in range(0, jc['JRK_CONTROL_PIN_COUNT']):
            self.pin_info.append(type('pinfo_'+str(i), (object,), {})())

        self._convert_structure_to_readonly_properties()

    def _convert_structure_to_readonly_properties(self):
        for field_name, field_type in jrk_variables._fields_:
            if not field_name == 'pin_info':
                prop = property(fget=partial(self._get_jrk_readonly_property, field_name))
                setattr(self.__class__, field_name, prop)
        
        for i in range(0, jc['JRK_CONTROL_PIN_COUNT']):
            for field_name, field_type in pin_info._fields_:
                prop = property(fget=partial(self._get_pin_readonly_property, field_name, i))
                setattr(self.pin_info[i].__class__, field_name, prop)

    @JED
    def _update_jrk_variables(self):
        e_p = self.jrklib.jrk_get_variables(byref(self._device_handle), \
                                       byref(self._jrk_variables_p), c_bool(True))
        self._jrk_variables = self._jrk_variables_p[0]
        return e_p

    def _get_jrk_readonly_property(self, field_name, _):
        self._update_jrk_variables()
        value = getattr(self._jrk_variables, field_name)
        if field_name == "error_status" or field_name == "error_occurred":
            self._convert_error_bitmask(value)
        return value

    def _get_pin_readonly_property(self, field_name, pin_num, _):
        self._update_jrk_variables()
        return getattr(self._jrk_variables.pin_info[pin_num], field_name)

    def _convert_error_bitmask(self, e_bit_mask):
        ecodes = ["JRK_ERROR_AWAITING_COMMAND",
                  "JRK_ERROR_NO_POWER",
                  "JRK_ERROR_MOTOR_DRIVER",
                  "JRK_ERROR_INPUT_INVALID",
                  "JRK_ERROR_INPUT_DISCONNECT",
                  "JRK_ERROR_FEEDBACK_DISCONNECT",
                  "JRK_ERROR_SOFT_OVERCURRENT",
                  "JRK_ERROR_SERIAL_SIGNAL",
                  "JRK_ERROR_SERIAL_OVERRUN",
                  "JRK_ERROR_SERIAL_BUFFER_FULL",
                  "JRK_ERROR_SERIAL_CRC",
                  "JRK_ERROR_SERIAL_PROTOCOL",
                  "JRK_ERROR_SERIAL_TIMEOUT",
                  "JRK_ERROR_HARD_OVERCURRENT"]
        for code in ecodes:
            if ((e_bit_mask >> jc[code]) & 1):
                self._logger.error(code)

        
class PyJrk_Settings(object):
    def __init__(self, device_handle, driver_handles, product: int, logger: LoggerProtocol):
        self._device_handle = device_handle
        self.usblib, self.jrklib = driver_handles
        self._logger = logger

        # local vs device - local settings on pc, device settings on jrk
        self._local_settings = jrk_settings()
        self._device_settings = jrk_settings()
        self._device_settings_p = POINTER(jrk_settings)()
        
        self._convert_structure_to_properties()
        self.auto_apply = True

        self._fill_with_defaults()

    # Maybe useful, need to # TEST
    def _create_jrk_settings(self):
        e_p = self.jrklib.jrk_settings_create(byref(self._device_settings_p))
        return e_p

    def _convert_structure_to_properties(self):
        for field_name, field_type in jrk_settings._fields_:
            prop = property(fget=partial(self._get_jrk_settings_from_device, field_name),
                            fset=partial(self._set_jrk_settings_with_option, field_name))
            setattr(self.__class__, field_name, prop)

    def _get_jrk_settings_from_device(self, field_name, _):
        self._pull_device_settings()
        return getattr(self._device_settings, field_name)

    def _set_jrk_settings_with_option(self, field_name, _, value):
        setattr(self._local_settings, field_name, value)
        if (self.auto_apply):
            self.apply()
        
    @JED
    def _pull_device_settings(self):
        """Gets the current settings stored in the device's EEPROM memory.
        
        This method reads the current settings from the device's EEPROM and stores 
        them in _device_settings. This function is always called before calling a 
        getting a setting from the device via properties in order to refresh the settings.
        """
        e_p = self.jrklib.jrk_get_eeprom_settings(byref(self._device_handle),
                                      byref(self._device_settings_p))
        self._device_settings = self._device_settings_p[0]
        return e_p

    @JED
    def _set_settings(self):
        """Sets the controller settings based on _local_settings.

        This method writes the previously configured settings stored in _local_settings 
        to the device's EEPROM memory. The _local_settings variable must be properly 
        set before calling this method.
        """
        e_p = self.jrklib.jrk_set_eeprom_settings(byref(self._device_handle),
                                      byref(self._local_settings))
        return e_p
        
    def _fill_with_defaults(self):
        """jrk_settings_fill_with_defaults is not available on the windows DLL. Thus, a combination of restore defaults and get_eeprom_settings is used to 
        restore the JRK setting to their default and then retrieve them to fill the local settings."""
        self._jrk_restore_defaults()
        self._pull_device_settings()
        self._local_settings = self._device_settings_p[0]
        self._logger.debug("Settings restored to factory defaults")

    def apply(self):
        self._settings_fix()
        self._set_settings()
        self._reinitialize()

    @JED
    def _settings_fix(self):
        warnings_p = POINTER(c_char_p)()
        e_p = self.jrklib.jrk_settings_fix(byref(self._local_settings),warnings_p)
        if bool(warnings_p):
            for w in warnings_p:
                self._logger.warning(w)
        return e_p

    @JED
    def _reinitialize(self):
        e_p = self.jrklib.jrk_reinitialize(byref(self._device_handle))
        return e_p
            
    @JED
    def _settings_to_string(self):
        settings_str = c_char_p()
        self._pull_device_settings()
        e_p = self.jrklib.jrk_settings_to_string(byref(self._device_settings), byref(settings_str))
        self._logger.info(f"Device settings:\n{settings_str.value.decode()}")
        return e_p
    
    @JED
    def _jrk_restore_defaults(self):
        e_p = self.jrklib.jrk_restore_defaults(byref(self._device_handle))
        return e_p
    
    def print_settings(self):
        self._settings_to_string()

    def load_config(self, config_file):
        with open(config_file, 'r') as ymlfile:
            cfg = yaml.safe_load(ymlfile)

        cfg_settings = cfg['jrk_settings']

        jrk_settings_list = [setting_name for setting_name, setting_type in jrk_settings._fields_]

        for setting in cfg_settings: 
            if setting in jrk_settings_list:
                if 'JRK' in str(cfg_settings[setting]):
                    value = jc[cfg_settings[setting]]
                else:
                    value = cfg_settings[setting]
                setattr(self._local_settings, setting, value)

        if (self.auto_apply):
            self.apply()

if __name__ == '__main__':

    jrk = PyJrk()
    print(jrk.list_connected_device_serial_numbers())