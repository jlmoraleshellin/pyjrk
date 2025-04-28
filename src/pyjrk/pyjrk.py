import os
import yaml
from ctypes import *
from .pyjrk_protocol import jrk_constant as jc
from .pyjrk_structures import *
from functools import wraps, partial
import logging
import platform

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
    def __init__(self, log_file=None):
        self._load_drivers()
        self._logger = self._initialize_logger()
        self.device = None
        self.handle = None
        self.settings = None
        self.variables = None
        self._commands = [('set_target', c_uint16),
                          ('stop_motor', None),
                          ('force_duty_cycle_target', None),
                          ('force_duty_cycle', None)
                          ('reinitialize', c_uint8),]
        self._create_jrk_command_attributes()

    def _initialize_logger(self):
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
            pass
            self.usblib = windll.LoadLibrary(file_path + "\\drivers\\x64\\libusbp-1.dll") # type: ignore
            self.jrklib = windll.LoadLibrary(file_path + "\\drivers\\x64\\libpololu-jrk2-1.dll") # type: ignore
        elif platform.system() == 'Linux':
            # Linux shared library paths
            self.usblib = CDLL(file_path + "/drivers/linux/libusbp-1.so")
            self.jrklib = CDLL(file_path + "/drivers/linux/libpololu-jrk2-1.so")

    def _create_jrk_command_attributes(self):
        for c in self._commands:
            if bool(c[1]):
                setattr(self.__class__, c[0], partial(self._jrk_command_with_value, c[0], c[1]))
            else:
                setattr(self.__class__, c[0], partial(self._jrk_command, c[0]))

    @JED
    def _jrk_command(self, cmd_name):
        e_p = getattr(self.jrklib,'jrk_'+ cmd_name)(byref(self.handle))
        return e_p

    @JED
    def _jrk_command_with_value(self, cmd_name, c_type, value):
        if 'JRK' in str(value):
            value = jc[value]
        e_p = getattr(self.jrklib,'jrk_'+ cmd_name)(byref(self.handle), c_type(value))
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
            print("No Jrk devices connected.")
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
                self.variables = PyJrk_Variables(self.handle, (self.usblib, self.jrklib))
                # TEST there is no product field in PyJrk_variables
                # Maybe retrieve product from the jrk_device object, otherwise provide through config
                self.settings = PyJrk_Settings(self.handle, (self.usblib, self.jrklib), int(self.device.product))
                return 0
        if not self.device:
            self._logger.error("Serial number device not found.")
            return 1


class PyJrk_Variables(object):
    def __init__(self, device_handle, driver_handles):
        self.usblib, self.jrklib = driver_handles
        self._logger = logging.getLogger('PyJrk')
        self._device_handle = device_handle
        self._jrk_variables_p = POINTER(jrk_variables)()
        self._jrk_variables = jrk_variables()
        
        self.pin_info = []
        for i in range(0, jc['JRK_CONTROL_PIN_COUNT']):
            self.pin_info.append(type('pinfo_'+str(i), (object,), {})())

        self._convert_structure_to_readonly_properties()

    def _convert_structure_to_readonly_properties(self):
        for field in jrk_variables._fields_:
            if not field[0] == 'pin_info':
                prop = property(fget=partial(self._get_jrk_readonly_property, field[0]))
                setattr(self.__class__, field[0], prop)
        
        for i in range(0, jc['JRK_CONTROL_PIN_COUNT']):
            for field in pin_info._fields_:
                prop = property(fget=partial(self._get_pin_readonly_property, field[0], i))
                setattr(self.pin_info[i].__class__, field[0], prop)

    @JED
    def _update_jrk_variables(self):
        e_p = self.jrklib.jrk_get_variables(byref(self._device_handle), \
                                       byref(self._jrk_variables_p), c_bool(True))
        self._jrk_variables = self._jrk_variables_p[0]
        return e_p

    def _get_jrk_readonly_property(self, field, obj):
        self._update_jrk_variables()
        value = getattr(self._jrk_variables, field)
        if field == "error_status" or field == "error_occurred":
            self._convert_error_bitmask(value)
        return value

    def _get_pin_readonly_property(self, field, pin_num, obj):
        self._update_jrk_variables()
        return getattr(self._jrk_variables.pin_info[pin_num], field)

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
    def __init__(self, device_handle, driver_handles, product: int):
        self.usblib, self.jrklib = driver_handles
        self._logger = logging.getLogger('PyJrk')
        self._device_handle = device_handle
        # local vs device - local settings on pc, device settings on jrk
        self._local_settings = jrk_settings()
        self._device_settings = jrk_settings()
        self._device_settings_p = POINTER(jrk_settings)()
        
        self._convert_structure_to_properties()
        self.auto_apply = False

        # If retrieved from the device it should already be an int and protocol dict should
        # not need to be accessed.
        #if "JRK" in str(product):
        #    product = int(jc[product])
        self._fill_with_defaults(product)

    def _convert_structure_to_properties(self):
        for field in jrk_settings._fields_:
            prop = property(fget=partial(self._get_jrk_settings_from_device, field[0]),
                            fset=partial(self._set_jrk_settings_with_option, field[0]))
            setattr(self.__class__, field[0], prop)

    def _get_jrk_settings_from_device(self, field, obj):
        self._pull_device_settings()
        return getattr(self._device_settings, field)

    def _set_jrk_settings_with_option(self, field, obj, value):
        setattr(self._local_settings, field, value)
        if (self.auto_apply):
            self.apply()
        
    @JED
    def _pull_device_settings(self):
        e_p = self.jrklib.jrk_get_settings(byref(self._device_handle),
                                      byref(self._device_settings_p))
        self._device_settings = self._device_settings_p[0]
        return e_p

    @JED
    def _set_settings(self):
        e_p = self.jrklib.jrk_set_settings(byref(self._device_handle),
                                      byref(self._local_settings))
        return e_p
        
    def _fill_with_defaults(self, product):
        self._local_settings.product = product
        self.jrklib.jrk_settings_fill_with_defaults(byref(self._local_settings))

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
    
    def print_settings(self):
        self._settings_to_string()

    def load_config(self, config_file):
        with open(config_file, 'r') as ymlfile:
            cfg = yaml.safe_load(ymlfile)

        cfg_settings = cfg['jrk_settings']

        jrk_settings_list = []
        for setting in jrk_settings._fields_:
            jrk_settings_list.append(setting[0])

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